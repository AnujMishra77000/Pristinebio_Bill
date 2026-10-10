from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import ensure_branch_access
from app.models.enums import InvoiceStatus
from app.models.integration import IntegrationAuditLog, IntegrationReconciliation, OutboundIntegrationJob
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.integration import IntegrationJobCreate, ProviderResponse
from app.services.idempotency import canonical_payload_hash, normalize_idempotency_key

MAX_ATTEMPTS = 3
UNAVAILABLE_REASON = "No provider documentation, credentials, sandbox or approved mappings are configured"
SUPPORTED_PROVIDERS: frozenset[str] = frozenset()


def validate_provider_response(payload: dict) -> ProviderResponse:
    """Validate the only response shape a future adapter may persist."""
    try:
        return ProviderResponse.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(502, "External provider response failed validation") from exc


def normalize_key(value: str | None) -> str:
    try:
        normalized = normalize_idempotency_key(value)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if normalized is None:
        raise HTTPException(422, "Idempotency-Key is required for integration job creation")
    return normalized


def _snapshot(job: OutboundIntegrationJob) -> dict:
    return {"status": job.status, "attempt_count": job.attempt_count, "external_status": job.external_status, "external_reference": job.external_reference}


def _audit(db: Session, user: User, job: OutboundIntegrationJob, action: str, reason: str | None, before: dict | None, after: dict | None) -> None:
    db.add(IntegrationAuditLog(job_id=job.id, actor_user_id=user.id, action=action, reason=reason, before=before, after=after))


def _open_reconciliation(db: Session, job: OutboundIntegrationJob, difference_type: str, details: dict) -> None:
    reconciliation = db.scalar(
        select(IntegrationReconciliation)
        .where(IntegrationReconciliation.job_id == job.id, IntegrationReconciliation.status == "open")
        .with_for_update()
    )
    if reconciliation is None:
        db.add(IntegrationReconciliation(
            job_id=job.id, difference_type=difference_type, status="open", local_status=job.invoice.status.value,
            external_status=job.external_status, external_reference=job.external_reference, details=details,
        ))
    else:
        reconciliation.difference_type = difference_type
        reconciliation.local_status = job.invoice.status.value
        reconciliation.external_status = job.external_status
        reconciliation.external_reference = job.external_reference
        reconciliation.details = details


def _get_invoice(db: Session, user: User, request: IntegrationJobCreate) -> Invoice:
    invoice = db.scalar(select(Invoice).where(Invoice.id == request.invoice_id).with_for_update())
    if invoice is None:
        raise HTTPException(404, "Invoice not found")
    ensure_branch_access(user, invoice.branch_id)
    if request.branch_id is not None and request.branch_id != invoice.branch_id:
        raise HTTPException(422, "Invoice and integration branch do not match")
    if invoice.status not in {InvoiceStatus.APPROVED, InvoiceStatus.PDF_GENERATED}:
        raise HTTPException(422, "Only approved invoices can be submitted to an external integration")
    return invoice


def create_job(db: Session, user: User, request: IntegrationJobCreate, idempotency_key: str) -> tuple[OutboundIntegrationJob, bool]:
    invoice = _get_invoice(db, user, request)
    payload_hash = canonical_payload_hash(request)
    existing = db.scalar(select(OutboundIntegrationJob).where(
        OutboundIntegrationJob.branch_id == invoice.branch_id,
        OutboundIntegrationJob.idempotency_key == idempotency_key,
    ))
    if existing is not None:
        if existing.payload_hash != payload_hash:
            raise HTTPException(409, "Idempotency-Key was already used with a different integration payload")
        return existing, True

    job = OutboundIntegrationJob(
        branch_id=invoice.branch_id, invoice_id=invoice.id, created_by_id=user.id,
        provider_key=request.provider_key, operation=request.operation, idempotency_key=idempotency_key,
        payload_hash=payload_hash, status="queued" if request.provider_key in SUPPORTED_PROVIDERS else "unavailable",
        max_attempts=MAX_ATTEMPTS, request_snapshot=request.model_dump(mode="json"),
        last_error_code=None if request.provider_key in SUPPORTED_PROVIDERS else "provider_unconfigured",
        last_error_message=None if request.provider_key in SUPPORTED_PROVIDERS else UNAVAILABLE_REASON,
    )
    db.add(job)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(OutboundIntegrationJob).where(
            OutboundIntegrationJob.branch_id == invoice.branch_id,
            OutboundIntegrationJob.idempotency_key == idempotency_key,
        ))
        if existing is None:
            raise HTTPException(409, "Integration request is being finalized; retry the same request") from None
        if existing.payload_hash != payload_hash:
            raise HTTPException(409, "Idempotency-Key was already used with a different integration payload")
        return existing, True

    if job.status == "unavailable":
        db.flush()
        _open_reconciliation(db, job, "provider_unavailable", {"reason": UNAVAILABLE_REASON, "provider_key": job.provider_key})
    _audit(db, user, job, "created", None, None, _snapshot(job))
    db.commit()
    db.refresh(job)
    return job, False


def retry_job(db: Session, user: User, job_id: int) -> OutboundIntegrationJob:
    job = db.scalar(select(OutboundIntegrationJob).where(OutboundIntegrationJob.id == job_id).with_for_update())
    if job is None:
        raise HTTPException(404, "Integration job not found")
    ensure_branch_access(user, job.branch_id)
    if job.status in {"accepted", "reconciled", "cancelled"}:
        raise HTTPException(409, "This integration job cannot be retried in its current state")
    before = _snapshot(job)
    if job.attempt_count >= job.max_attempts:
        job.status = "failed"
        job.last_error_code = "retry_exhausted"
        job.last_error_message = f"Maximum of {job.max_attempts} attempts reached"
        _open_reconciliation(db, job, "retry_exhausted", {"reason": job.last_error_message})
        _audit(db, user, job, "retry_exhausted", None, before, _snapshot(job))
    else:
        job.attempt_count += 1
        if job.provider_key in SUPPORTED_PROVIDERS:
            job.status = "queued"
            job.last_error_code = None
            job.last_error_message = None
        else:
            job.status = "unavailable"
            job.last_error_code = "provider_unconfigured"
            job.last_error_message = UNAVAILABLE_REASON
            _open_reconciliation(db, job, "provider_unavailable", {"reason": UNAVAILABLE_REASON, "attempt": job.attempt_count})
        _audit(db, user, job, "retry_requested", None, before, _snapshot(job))
    db.commit()
    db.refresh(job)
    return job


def cancel_job(db: Session, user: User, job_id: int, reason: str) -> OutboundIntegrationJob:
    job = db.scalar(select(OutboundIntegrationJob).where(OutboundIntegrationJob.id == job_id).with_for_update())
    if job is None:
        raise HTTPException(404, "Integration job not found")
    ensure_branch_access(user, job.branch_id)
    if job.status in {"accepted", "cancelled"}:
        raise HTTPException(409, "This integration job cannot be cancelled in its current state")
    before = _snapshot(job)
    job.status = "cancelled"
    reconciliation = db.scalar(select(IntegrationReconciliation).where(
        IntegrationReconciliation.job_id == job.id, IntegrationReconciliation.status == "open"
    ).with_for_update())
    if reconciliation is not None:
        reconciliation.status = "resolved"
        reconciliation.resolved_at = datetime.now(UTC)
        reconciliation.resolved_by_id = user.id
        reconciliation.resolution_note = reason
    _audit(db, user, job, "cancelled", reason, before, _snapshot(job))
    db.commit()
    db.refresh(job)
    return job
