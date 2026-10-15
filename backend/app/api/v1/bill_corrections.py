"""The correction boundary deliberately leaves all ordinary bill routes intact."""
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import assigned_branch_ids, get_current_active_user, require_roles
from app.db.session import get_db
from app.models.bill_correction import BillCorrection
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.bill_correction import CorrectionAction, CorrectionRestart, InvoiceCorrectionUpdate, PurchaseOrderCorrectionUpdate
from app.services import bill_corrections as service
from app.services.invoice_pdf import PdfLayoutError

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_current_active_user)]
Approver = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))]
Collection = Literal["invoices", "purchase-orders"]


@router.get("/bill-corrections/pending")
def pending_corrections(db: Db, user: Approver, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100)):
    query = select(BillCorrection).where(BillCorrection.status == "pending_approval")
    if user.role != UserRole.ADMIN:
        query = query.where(BillCorrection.branch_id.in_(assigned_branch_ids(user)))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(BillCorrection.updated_at, BillCorrection.id).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for row in rows:
        document = row.working_snapshot["document"]
        items.append({
            "collection": "invoices" if row.invoice_id else "purchase-orders",
            "document_id": row.invoice_id or row.purchase_order_id,
            "document_type": document["document_type"],
            "document_number": document.get("invoice_number") or document.get("purchase_order_number"),
            "version": row.version, "reason": row.reason,
            "previous_final_total": row.original_snapshot["document"]["final_total"],
            "final_total": document["final_total"], "created_by_id": row.created_by_id,
            "submitted_by_id": row.submitted_by_id,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{collection}/{document_id}/correction")
def get_correction(collection: Collection, document_id: int, db: Db, user: Actor, edit: bool = False):
    bill, correction = service.load(db, user, collection, document_id)
    if correction and correction.status == "confirmed" and not edit:
        return service.read_original(collection, bill)
    service.ensure_eligible(db, bill)
    service.require_base(bill, correction)
    return service.read_view(collection, bill, correction, user)


@router.patch("/invoices/{document_id}/correction")
def save_invoice_correction(document_id: int, request: InvoiceCorrectionUpdate, db: Db, user: Actor):
    return service.save(db, user, "invoices", document_id, request)


@router.patch("/purchase-orders/{document_id}/correction")
def save_purchase_correction(document_id: int, request: PurchaseOrderCorrectionUpdate, db: Db, user: Actor):
    return service.save(db, user, "purchase-orders", document_id, request)


@router.post("/{collection}/{document_id}/correction/submit")
def submit_correction(collection: Collection, document_id: int, request: CorrectionAction, db: Db, user: Actor):
    return service.transition(db, user, collection, document_id, request, "submit")


@router.post("/{collection}/{document_id}/correction/approve")
def approve_correction(collection: Collection, document_id: int, request: CorrectionAction, db: Db, user: Approver):
    return service.transition(db, user, collection, document_id, request, "approve")


@router.post("/{collection}/{document_id}/correction/return")
def return_correction(collection: Collection, document_id: int, request: CorrectionAction, db: Db, user: Approver):
    return service.transition(db, user, collection, document_id, request, "return")


@router.post("/{collection}/{document_id}/correction/restart")
def restart_correction(collection: Collection, document_id: int, request: CorrectionRestart, db: Db, user: Approver):
    return service.restart(db, user, collection, document_id, request)


@router.post("/{collection}/{document_id}/correction/preview-pdf")
def preview_correction(collection: Collection, document_id: int, request: CorrectionAction, db: Db, user: Actor):
    bill, correction = service.load(db, user, collection, document_id, lock=True)
    service.ensure_eligible(db, bill)
    service.require_base(bill, correction)
    if not correction or correction.status == "confirmed":
        raise service.error("correction_not_saved", "Save this correction before previewing it.")
    service.require_version(correction.version, request.expected_version)
    working = service.working_view(collection, bill, correction, user)
    api = service.domain(collection)[3]
    context_builder = api._invoice_pdf_context if collection == "invoices" else api._purchase_order_pdf_context
    renderer = api.render_invoice_pdf if collection == "invoices" else api.render_purchase_order_pdf
    try:
        result = renderer(context_builder(db, working, datetime.now(UTC)))
    except PdfLayoutError as exc:
        from fastapi import HTTPException
        raise HTTPException(422, str(exc)) from exc
    return Response(result.pdf_bytes, media_type="application/pdf", headers={"Cache-Control": "no-store", "Content-Disposition": f'inline; filename="correction-{document_id}-preview.pdf"'})
