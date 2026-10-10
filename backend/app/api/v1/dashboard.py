from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import assigned_branch_ids, get_current_active_user
from app.db.session import get_db
from app.models.enums import InvoiceStatus, UserRole
from app.models.invoice import Invoice, InvoiceAuditLog
from app.models.purchase_order import PurchaseOrder, PurchaseOrderAuditLog
from app.models.user import User


router = APIRouter()


def _scoped(statement, model, current_user: User):
    if current_user.role == UserRole.ADMIN:
        return statement
    assigned = assigned_branch_ids(current_user)
    return statement.where(model.branch_id.in_(assigned) if assigned else false())


@router.get("")
def dashboard_summary(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> dict:
    invoices = _scoped(select(Invoice), Invoice, current_user)
    sales_invoices = _scoped(select(Invoice).where(Invoice.document_type == "sales"), Invoice, current_user)
    reagent_invoices = _scoped(select(Invoice).where(Invoice.document_type == "reagent"), Invoice, current_user)
    purchase_orders = _scoped(select(PurchaseOrder), PurchaseOrder, current_user)
    pending_invoices = _scoped(select(Invoice).where(Invoice.status == InvoiceStatus.PENDING_APPROVAL), Invoice, current_user)
    pending_pos = _scoped(select(PurchaseOrder).where(PurchaseOrder.status == "pending_approval"), PurchaseOrder, current_user)
    draft_invoices = _scoped(select(Invoice).where(Invoice.status == InvoiceStatus.DRAFT), Invoice, current_user)
    draft_pos = _scoped(select(PurchaseOrder).where(PurchaseOrder.status == "draft"), PurchaseOrder, current_user)

    invoice_audits = select(InvoiceAuditLog).join(Invoice, Invoice.id == InvoiceAuditLog.invoice_id)
    po_audits = select(PurchaseOrderAuditLog).join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderAuditLog.purchase_order_id)
    if current_user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(current_user)
        predicate = Invoice.branch_id.in_(assigned) if assigned else false()
        invoice_audits = invoice_audits.where(predicate)
        po_audits = po_audits.where(PurchaseOrder.branch_id.in_(assigned) if assigned else false())
    activity = [
        {"document_type": "invoice", "document_id": row.invoice_id, "action": row.to_status.value, "actor_user_id": row.actor_user_id, "created_at": row.created_at.isoformat(), "note": row.note}
        for row in db.scalars(invoice_audits.order_by(InvoiceAuditLog.created_at.desc()).limit(8))
    ] + [
        {"document_type": "purchase_order", "document_id": row.purchase_order_id, "action": row.to_status, "actor_user_id": row.actor_user_id, "created_at": row.created_at.isoformat(), "note": row.note}
        for row in db.scalars(po_audits.order_by(PurchaseOrderAuditLog.created_at.desc()).limit(8))
    ]
    activity.sort(key=lambda item: item["created_at"], reverse=True)
    return {
        "invoice_count": db.scalar(select(func.count()).select_from(invoices.subquery())) or 0,
        "sales_invoice_count": db.scalar(select(func.count()).select_from(sales_invoices.subquery())) or 0,
        "reagent_invoice_count": db.scalar(select(func.count()).select_from(reagent_invoices.subquery())) or 0,
        "purchase_order_count": db.scalar(select(func.count()).select_from(purchase_orders.subquery())) or 0,
        "domestic_oils_purchase_order_count": db.scalar(select(func.count()).select_from(purchase_orders.where(PurchaseOrder.document_type == "domestic_oils").subquery())) or 0,
        "reagent_purchase_order_count": db.scalar(select(func.count()).select_from(purchase_orders.where(PurchaseOrder.document_type == "reagent").subquery())) or 0,
        "draft_invoices": db.scalar(select(func.count()).select_from(draft_invoices.subquery())) or 0,
        "draft_purchase_orders": db.scalar(select(func.count()).select_from(draft_pos.subquery())) or 0,
        "pending_invoice_approvals": db.scalar(select(func.count()).select_from(pending_invoices.subquery())) or 0,
        "pending_purchase_order_approvals": db.scalar(select(func.count()).select_from(pending_pos.subquery())) or 0,
        "recent_activity": activity[:8],
    }
