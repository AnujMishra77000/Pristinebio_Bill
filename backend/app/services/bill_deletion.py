"""Explicit Admin deletion; private PDF cleanup is durable and retryable.

Database deletion and its minimal audit commit together. Files are removed only
after that commit, so a database rollback never loses a live bill's PDF. A file
failure returns 503, retaining the exact cleanup names in the independent audit;
repeating the same confirmed DELETE resumes cleanup without restoring the bill.
"""
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import ensure_branch_access
from app.core.config import get_settings
from app.models.authentication import SecurityAudit
from app.models.bill_correction import BillCorrection
from app.models.enums import UserRole
from app.models.integration import OutboundIntegrationJob
from app.models.invoice import Invoice, InvoiceCreationRequest, InvoiceRevision
from app.models.payment import ReceiptAllocation
from app.models.purchase_order import PurchaseOrder, PurchaseOrderCreationRequest, PurchaseOrderRevision
from app.models.user import User
from app.schemas.common import BillDeleteRequest

ACTION = "bill_permanently_deleted"


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def _file_path(name: str) -> Path:
    directory = Path(get_settings().pdf_storage_dir).resolve()
    if not name or Path(name).name != name or "\\" in name:
        raise _error(503, "invalid_pdf_path", "Stored PDF path is invalid. Deletion was not completed; contact the administrator.")
    path = directory / name
    if path.is_symlink() or path.resolve().parent != directory or (path.exists() and not path.is_file()):
        raise _error(503, "invalid_pdf_path", "Stored PDF path is unsafe. Deletion was not completed; contact the administrator.")
    return path


def _owned_pdf_names(db: Session, bill: Invoice | PurchaseOrder, entity: str) -> list[str]:
    # Never infer ownership from a filename/ID: old imports or resets may have
    # reused IDs. Only this document's explicit database references are eligible.
    names = set()
    if bill.pdf_storage_key: names.add(bill.pdf_storage_key)
    for revision in bill.revisions:
        snapshot = revision.snapshot or {}
        historical = snapshot.get("document", snapshot).get("pdf_storage_key")
        if historical: names.add(historical)
    for name in names: _file_path(name)
    # Corrupt legacy shared references must not erase another document's PDF.
    for model in (Invoice, PurchaseOrder):
        statement = select(model.id).where(model.pdf_storage_key.in_(names))
        if isinstance(bill, model): statement = statement.where(model.id != bill.id)
        if names and db.scalar(statement.limit(1)) is not None:
            raise _error(409, "shared_pdf_reference", "This PDF is also referenced by another bill. Resolve the shared reference before deleting.")
    for model, owner in ((InvoiceRevision, InvoiceRevision.invoice_id), (PurchaseOrderRevision, PurchaseOrderRevision.purchase_order_id)):
        statement = select(model.id).where(or_(model.snapshot["pdf_storage_key"].as_string().in_(names), model.snapshot["document"]["pdf_storage_key"].as_string().in_(names)))
        if (entity == "invoice" and model is InvoiceRevision) or (entity == "purchase_order" and model is PurchaseOrderRevision):
            statement = statement.where(owner != bill.id)
        if names and db.scalar(statement.limit(1)) is not None:
            raise _error(409, "shared_pdf_reference", "This PDF belongs to another bill's saved revision. Resolve the shared reference before deleting.")
    return sorted(names)


def _cleanup(db: Session, audit: SecurityAudit) -> None:
    names = (audit.after or {}).get("pdf_cleanup_pending", [])
    try:
        for name in names: _file_path(name).unlink(missing_ok=True)
    except (OSError, HTTPException) as exc:
        raise _error(503, "pdf_cleanup_pending", "The bill record was deleted, but its PDF cleanup is incomplete. Retry Delete with the same bill number; contact the administrator if this continues.") from exc
    if names:
        audit.after = {"deleted": True, "pdf_cleanup_pending": []}
        try: db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise _error(503, "pdf_cleanup_pending", "PDF cleanup needs confirmation. Retry Delete with the same bill number.") from exc


def delete_bill(db: Session, user: User, entity: Literal["invoice", "purchase_order"], document_id: int, request: BillDeleteRequest) -> None:
    if user.role != UserRole.ADMIN:
        raise _error(403, "admin_required", "Only Admin can permanently delete bills.")
    model = Invoice if entity == "invoice" else PurchaseOrder
    bill = db.scalar(select(model).where(model.id == document_id).with_for_update())
    if bill is None:
        audit = db.scalar(select(SecurityAudit).where(SecurityAudit.entity_type == entity, SecurityAudit.entity_id == str(document_id), SecurityAudit.action == ACTION)
                          .order_by(SecurityAudit.id.desc()).limit(1).with_for_update())
        if audit is None: raise _error(404, "bill_not_found", "Bill not found.")
        before = audit.before or {}
        ensure_branch_access(user, before["branch_id"])
        if (before.get("document_number"), before.get("version"), before.get("document_type")) != (request.confirmation_number, request.expected_version, request.document_type):
            raise _error(409, "delete_confirmation_mismatch", "The deletion confirmation does not match this bill.")
        _cleanup(db, audit)
        return
    ensure_branch_access(user, bill.branch_id)
    number = (bill.invoice_number or f"Draft #{bill.id}") if entity == "invoice" else bill.purchase_order_number
    if bill.version != request.expected_version:
        raise _error(409, "version_conflict", "This bill changed. Reload it and confirm its latest revision before deleting.")
    if number != request.confirmation_number or bill.document_type != request.document_type:
        raise _error(409, "delete_confirmation_mismatch", "Enter the exact bill number and delete from its matching register.")
    if entity == "invoice":
        if db.scalar(select(ReceiptAllocation.id).where(ReceiptAllocation.invoice_id == bill.id).limit(1)) is not None:
            raise _error(409, "bill_has_payments", "This bill has payment allocation history and cannot be deleted. Payment records were not changed.")
        if db.scalar(select(OutboundIntegrationJob.id).where(OutboundIntegrationJob.invoice_id == bill.id).limit(1)) is not None:
            raise _error(409, "bill_has_integrations", "This bill has integration records and cannot be deleted. Integration history was not changed.")
    names = _owned_pdf_names(db, bill, entity)
    deleted_at = datetime.now(UTC)
    audit = SecurityAudit(actor_id=user.id, action=ACTION, entity_type=entity, entity_id=str(bill.id), created_at=deleted_at,
                          before={"branch_id": bill.branch_id, "document_number": number, "document_type": bill.document_type, "version": bill.version,
                                  "status": bill.status.value if hasattr(bill.status, "value") else bill.status},
                          after={"deleted": True, "pdf_cleanup_pending": names})
    db.add(audit)
    creation_model = InvoiceCreationRequest if entity == "invoice" else PurchaseOrderCreationRequest
    link = creation_model.invoice_id if entity == "invoice" else creation_model.purchase_order_id
    try:
        db.execute(update(creation_model).where(link == bill.id).values({link.key: None, "deleted_at": deleted_at}))
        correction_link = BillCorrection.invoice_id if entity == "invoice" else BillCorrection.purchase_order_id
        db.execute(delete(BillCorrection).where(correction_link == bill.id))
        db.delete(bill)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _error(409, "bill_has_dependencies", "Another record references this bill. Reload and resolve its linked records before deleting; no data was deleted.") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise _error(503, "delete_failed", "Deletion could not complete. The bill was retained; retry shortly.") from exc
    _cleanup(db, audit)
