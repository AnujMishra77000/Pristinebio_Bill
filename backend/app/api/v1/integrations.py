from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, require_roles
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.integration import IntegrationReconciliation, OutboundIntegrationJob
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.integration import (
    CancelIntegrationJob, IntegrationJobCreate, IntegrationJobRead, IntegrationPage, InvoiceIntegrationStatus,
    NumberingReview, ProviderRead, ReconciliationPage, ReconciliationRead,
)
from app.services.integration import UNAVAILABLE_REASON, cancel_job, create_job, normalize_key, retry_job


router = APIRouter()
OPERATORS = require_roles(UserRole.ADMIN, UserRole.MANAGER)


def _scope(statement, model, user: User):
    if user.role == UserRole.ADMIN:
        return statement
    assigned = assigned_branch_ids(user)
    return statement.where(model.branch_id.in_(assigned) if assigned else false())


def _job_response(job: OutboundIntegrationJob) -> IntegrationJobRead:
    return IntegrationJobRead.model_validate(job, from_attributes=True)


@router.get("/providers", response_model=list[ProviderRead])
def provider_readiness(_: Annotated[User, Depends(OPERATORS)]) -> list[ProviderRead]:
    return [ProviderRead(provider_key="client-configured-provider", available=False, environment="not-configured", reason=UNAVAILABLE_REASON)]


@router.get("/numbering-review", response_model=NumberingReview)
def numbering_review(_: Annotated[User, Depends(OPERATORS)]) -> NumberingReview:
    return NumberingReview(
        current_series="PBPL/{financial_year}/{staff_entered_suffix}",
        compatibility="Sales Invoices and Reagent Bills share one invoice-number namespace per Indian financial year. Staff enters the suffix on each draft; shared uniqueness prevents cross-type duplicates, and each register keeps its own document count. Existing issued invoice numbers are preserved, and external compatibility has not been approved by accounting.",
        proposed_series="No numbering change proposed",
        migration_policy="Do not renumber issued documents. Any future provider-specific series requires written accounting approval, a forward-only effective date, and a reconciliation plan.",
    )


@router.post("/jobs", response_model=IntegrationJobRead, status_code=201)
def create_integration_job(
    request: IntegrationJobCreate,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    db: Session = Depends(get_db),
    user: User = Depends(OPERATORS),
) -> IntegrationJobRead:
    job, replay = create_job(db, user, request, normalize_key(idempotency_key))
    response.headers["X-Idempotent-Replay"] = str(replay).lower()
    return _job_response(job)


@router.get("/jobs", response_model=IntegrationPage)
def list_integration_jobs(
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    status: str | None = Query(None, max_length=20), provider_key: str | None = Query(None, max_length=80),
    invoice_id: int | None = Query(None, ge=1), db: Session = Depends(get_db), user: User = Depends(OPERATORS),
) -> IntegrationPage:
    statement = _scope(select(OutboundIntegrationJob), OutboundIntegrationJob, user)
    if status and status.strip():
        statement = statement.where(OutboundIntegrationJob.status == status.strip().lower())
    if provider_key and provider_key.strip():
        statement = statement.where(OutboundIntegrationJob.provider_key == provider_key.strip().lower())
    if invoice_id is not None:
        statement = statement.where(OutboundIntegrationJob.invoice_id == invoice_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    jobs = db.scalars(statement.order_by(OutboundIntegrationJob.created_at.desc(), OutboundIntegrationJob.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return IntegrationPage(items=[_job_response(job) for job in jobs], total=total, page=page, page_size=page_size)


@router.post("/jobs/{job_id}/retry", response_model=IntegrationJobRead)
def retry_integration_job(job_id: int, db: Session = Depends(get_db), user: User = Depends(OPERATORS)) -> IntegrationJobRead:
    return _job_response(retry_job(db, user, job_id))


@router.post("/jobs/{job_id}/cancel", response_model=IntegrationJobRead)
def cancel_integration_job(job_id: int, request: CancelIntegrationJob, db: Session = Depends(get_db), user: User = Depends(OPERATORS)) -> IntegrationJobRead:
    return _job_response(cancel_job(db, user, job_id, request.reason))


@router.get("/reconciliation", response_model=ReconciliationPage)
def list_reconciliation(
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), open_only: bool = True,
    db: Session = Depends(get_db), user: User = Depends(OPERATORS),
) -> ReconciliationPage:
    statement = select(IntegrationReconciliation).join(OutboundIntegrationJob, OutboundIntegrationJob.id == IntegrationReconciliation.job_id)
    statement = _scope(statement, OutboundIntegrationJob, user)
    if open_only:
        statement = statement.where(IntegrationReconciliation.status == "open")
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(statement.order_by(IntegrationReconciliation.detected_at.desc(), IntegrationReconciliation.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return ReconciliationPage(items=[ReconciliationRead.model_validate(item, from_attributes=True) for item in items], total=total, page=page, page_size=page_size)


@router.get("/invoices/{invoice_id}/status", response_model=InvoiceIntegrationStatus)
def invoice_integration_status(invoice_id: int, db: Session = Depends(get_db), user: User = Depends(OPERATORS)) -> InvoiceIntegrationStatus:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(404, "Invoice not found")
    ensure_branch_access(user, invoice.branch_id)
    jobs = db.scalars(select(OutboundIntegrationJob).where(OutboundIntegrationJob.invoice_id == invoice.id).order_by(OutboundIntegrationJob.created_at.desc())).all()
    return InvoiceIntegrationStatus(invoice_id=invoice.id, local_status=invoice.status.value, external_jobs=[_job_response(job) for job in jobs])
