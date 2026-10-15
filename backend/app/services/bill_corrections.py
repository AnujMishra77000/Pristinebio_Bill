"""Versioned working copies; the live document is published only on approval.

All writes lock the parent bill first, then its unique correction row. This is
the same parent lock used by payment allocation and ordinary bill transitions.
JSON stores Decimal strings and complete transaction snapshots, never masters.
"""
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

from fastapi import HTTPException
from sqlalchemy import Date, DateTime, Enum as SAEnum, Numeric, select
from sqlalchemy.orm import Session

from app.models.authentication import SecurityAudit
from app.models.bill_correction import BillCorrection
from app.models.enums import InvoiceStatus, UserRole
from app.models.integration import OutboundIntegrationJob
from app.models.invoice import Invoice, InvoiceAuditLog, InvoiceLine, InvoiceRevision
from app.models.payment import ReceiptAllocation
from app.models.purchase_order import PurchaseOrder, PurchaseOrderAuditLog, PurchaseOrderLine, PurchaseOrderRevision
from app.schemas.invoice import InvoiceRead, InvoiceUpdate
from app.schemas.purchase_order import PurchaseOrderRead, PurchaseOrderUpdate
from app.schemas.master_records import SupplierCreate


PDF_FIELDS = ("pdf_storage_key", "pdf_sha256", "pdf_template_version", "pdf_generated_at", "pdf_generated_by_id")


def error(code, message, status=409):
    return HTTPException(status, {"code": code, "message": message})


def domain(collection):
    # Import at the boundary to keep existing API/calculator/PDF interfaces intact.
    from app.api.v1 import invoices, purchase_orders
    return (Invoice, InvoiceLine, InvoiceRead, invoices) if collection == "invoices" else (PurchaseOrder, PurchaseOrderLine, PurchaseOrderRead, purchase_orders)


def snapshot(bill):
    def values(instance):
        result = {}
        for column in instance.__table__.columns:
            value = getattr(instance, column.key)
            if isinstance(value, Decimal):
                value = str(value.quantize(Decimal(1).scaleb(-column.type.scale), rounding=ROUND_HALF_UP))
            elif isinstance(value, (date, datetime)):
                value = value.isoformat()
            elif isinstance(value, Enum):
                value = value.value
            result[column.key] = deepcopy(value)
        return result
    return {"document": values(bill), "lines": [values(line) for line in bill.lines]}


def restore(collection, stored):
    model, line_model, _, _ = domain(collection)

    def values(cls, raw):
        result = {}
        for column in cls.__table__.columns:
            value = deepcopy(raw.get(column.key))
            if value is not None:
                if isinstance(column.type, Numeric):
                    value = Decimal(value)
                elif isinstance(column.type, DateTime):
                    value = datetime.fromisoformat(value)
                elif isinstance(column.type, Date):
                    value = date.fromisoformat(value)
                elif isinstance(column.type, SAEnum) and column.type.enum_class:
                    value = column.type.enum_class(value)
            result[column.key] = value
        return result

    bill = model(**values(model, stored["document"]))
    bill.lines = [line_model(**values(line_model, item)) for item in stored["lines"]]
    return bill


def load(db, user, collection, document_id, *, lock=False):
    _, _, _, api = domain(collection)
    getter = api._get_invoice if collection == "invoices" else api._get_purchase_order
    bill = getter(db, user, document_id, for_update=lock)
    column = BillCorrection.invoice_id if collection == "invoices" else BillCorrection.purchase_order_id
    query = select(BillCorrection).where(column == bill.id)
    correction = db.scalar(query.with_for_update() if lock else query)
    return bill, correction


def ensure_eligible(db, bill):
    if bill.status not in {"approved", "pdf_generated"}:
        raise error("correction_not_available", "Only confirmed bills can open a correction. Closed, cancelled or pending documents cannot be edited here.")
    if isinstance(bill, Invoice):
        if db.scalar(select(ReceiptAllocation.id).where(ReceiptAllocation.invoice_id == bill.id).limit(1)) is not None:
            raise error("bill_has_payments", "This bill has payment allocation history. An authorized accounting correction is required; its financial data was not changed.")
        if db.scalar(select(OutboundIntegrationJob.id).where(OutboundIntegrationJob.invoice_id == bill.id).limit(1)) is not None or any((bill.irn, bill.e_way_bill_number, bill.acknowledgement_number, bill.signed_qr_data)):
            raise error("bill_has_integrations", "This bill has external integration/GST references. Resolve its external correction policy before editing; the confirmed bill was not changed.")


def require_base(bill, correction):
    if correction and correction.status != "confirmed" and correction.base_version != bill.version:
        raise HTTPException(409, {"code": "version_conflict", "message": "The confirmed bill changed after this correction started. Ask Manager/Admin to restart the correction against the latest bill; the previous edits remain in audit history.", "correction_base_changed": True, "current_version": bill.version, "correction_version": correction.version})


def require_version(version, expected):
    if version != expected:
        raise error("version_conflict", "This correction was changed by another user. Reload its latest revision; your fields have not been overwritten.")


def working_view(collection, bill, correction, user):
    active = correction is not None and correction.status != "confirmed"
    view = restore(collection, correction.working_snapshot if active else snapshot(bill))
    view.status = InvoiceStatus(correction.status if active else "draft") if collection == "invoices" else correction.status if active else "draft"
    view.version = correction.version if active else bill.version
    view.created_by_id = correction.created_by_id if active else user.id
    view.submitted_by_id = correction.submitted_by_id if active else None
    view.submitted_revision = view.version if active and correction.status == "pending_approval" else None
    view.approved_revision = None
    view.approved_at = None
    for field in PDF_FIELDS:
        setattr(view, field, None)
    for index, line in enumerate(view.lines, 1):
        if line.id is None:
            line.id = -index
    return view


def read_view(collection, bill, correction, user):
    view = working_view(collection, bill, correction, user)
    _, _, schema, _ = domain(collection)
    result = schema.model_validate(view).model_dump(mode="json")
    # InvoiceRead historically omits these actor IDs, but correction reviewers
    # need them to enforce independent approval in the entry-page controls.
    result.update(created_by_id=view.created_by_id, submitted_by_id=view.submitted_by_id)
    active = correction is not None and correction.status != "confirmed"
    result["correction"] = {
        "base_version": correction.base_version if active else bill.version,
        "reason": correction.reason if active else "",
        "status": correction.status if active else "draft",
        "previous_final_total": str(bill.final_total),
    }
    return result


def read_original(collection, bill):
    return domain(collection)[2].model_validate(bill).model_dump(mode="json")


def restart(db, user, collection, document_id, request):
    if user.role not in {UserRole.ADMIN, UserRole.MANAGER}:
        raise error("approval_required", "Only Manager or Admin can restart a stale correction.", 403)
    bill, correction = load(db, user, collection, document_id, lock=True)
    ensure_eligible(db, bill)
    require_version(bill.version, request.expected_version)
    if correction is None or correction.status == "confirmed":
        raise error("correction_not_available", "There is no stale correction to restart.")
    require_version(correction.version, request.correction_version)
    if correction.base_version == bill.version:
        raise error("correction_not_stale", "The correction still belongs to this bill revision. Continue editing or return it for correction instead.")
    before = {"original": correction.original_snapshot, "working": correction.working_snapshot, "version": correction.version, "reason": correction.reason}
    correction.version = max(correction.version, bill.version) + 1
    correction.base_version = bill.version
    correction.original_snapshot = snapshot(bill)
    correction.working_snapshot = snapshot(bill)
    correction.status = "draft"
    correction.reason = request.reason
    correction.created_by_id = user.id
    correction.created_at = datetime.now(UTC)
    correction.submitted_by_id = correction.approved_by_id = None
    correction.working_snapshot = snapshot(working_view(collection, bill, correction, user))
    record_audit(db, user, collection, bill, "restarted", request.reason, before, correction.working_snapshot)
    db.commit()
    return read_view(collection, bill, correction, user)


def record_audit(db, user, collection, bill, action, reason, before=None, after=None):
    db.add(SecurityAudit(actor_id=user.id, action=f"bill_correction_{action}", entity_type="invoice" if collection == "invoices" else "purchase_order", entity_id=str(bill.id), created_at=datetime.now(UTC), before=before, after={"reason": reason, "snapshot": after}))
    model = InvoiceAuditLog if collection == "invoices" else PurchaseOrderAuditLog
    foreign_key = "invoice_id" if collection == "invoices" else "purchase_order_id"
    note = f"Correction {action}: {reason}"
    # Invoice transition notes are VARCHAR(255); the full reason and snapshots
    # remain lossless in SecurityAudit and the correction/revision records.
    if collection == "invoices" and len(note) > 255:
        note = note[:252] + "..."
    db.add(model(**{foreign_key: bill.id}, from_status=bill.status, to_status=bill.status, actor_user_id=user.id, note=note))


def save(db: Session, user, collection, document_id, request):
    bill, correction = load(db, user, collection, document_id, lock=True)
    ensure_eligible(db, bill)
    require_base(bill, correction)
    active = correction is not None and correction.status != "confirmed"
    require_version(correction.version if active else bill.version, request.expected_version)
    if active and correction.status != "draft":
        raise error("correction_submitted", "This correction is awaiting approval. It must be returned before further editing.")
    view = working_view(collection, bill, correction, user)
    before = snapshot(view)
    _, _, _, api = domain(collection)
    fields = request.model_dump(exclude_unset=True, exclude={"correction_reason"})
    try:
        if collection == "invoices":
            # Existing draft validation/calculation operates on a transient copy.
            if "invoice_number_suffix" in fields:
                intended_number = f"{api.invoice_number_prefix_for(request.invoice_date or bill.invoice_date)}{fields['invoice_number_suffix']}"
                if intended_number != bill.invoice_number:
                    raise error("issued_number_immutable", "A correction must keep the confirmed invoice number.")
                fields.pop("invoice_number_suffix")
            if request.invoice_date is not None and api.financial_year_for(request.invoice_date) != api.financial_year_for(bill.invoice_date):
                raise error("issued_number_immutable", "A correction cannot move a confirmed invoice into another financial year.")
            api._apply_update_payload(db, view, user, InvoiceUpdate.model_validate(fields))
            if view.invoice_number != bill.invoice_number or view.financial_year != bill.financial_year:
                raise error("issued_number_immutable", "A correction must keep the confirmed invoice number and financial year.")
            if any(getattr(view, field) != getattr(bill, field) for field in ("irn", "e_way_bill_number", "acknowledgement_number", "signed_qr_data", "e_way_bill_date", "acknowledgement_date")):
                raise error("external_references_immutable", "External GST references cannot be added or changed through a bill correction.")
        else:
            update = PurchaseOrderUpdate.model_validate(fields)
            details = update.reagent_details or update.domestic_details
            if details is not None and details.supplier is None and details.supplier_id == bill.supplier_id:
                # Forms submit a saved supplier ID, but a confirmed transaction's
                # supplier address/tax state must not refresh from today's master.
                supplier = SupplierCreate.model_validate({
                    "branch_id": bill.branch_id,
                    **{name: getattr(view, f"supplier_{name}") for name in ("name", "gstin", "pan", "phone", "email")},
                    "address": {name: getattr(view, f"supplier_{name}") for name in ("address_line1", "address_line2", "city", "state", "state_code", "postal_code")},
                })
                details.supplier = supplier
            api._apply_purchase_order_update(db, view, update)
            if view.purchase_order_number != bill.purchase_order_number:
                raise error("issued_number_immutable", "A correction must keep the confirmed PO number.")
        if not active:
            if correction is None:
                correction = BillCorrection(**{"invoice_id" if collection == "invoices" else "purchase_order_id": bill.id}, branch_id=bill.branch_id)
                db.add(correction)
            correction.base_version = bill.version
            correction.original_snapshot = snapshot(bill)
            correction.created_by_id = user.id
            correction.created_at = datetime.now(UTC)
            correction.submitted_by_id = correction.approved_by_id = None
        correction.status = "draft"
        correction.version = request.expected_version + 1
        correction.reason = request.correction_reason
        view.version = correction.version
        correction.working_snapshot = snapshot(view)
        record_audit(db, user, collection, bill, "saved", correction.reason, before, correction.working_snapshot)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return read_view(collection, bill, correction, user)


def transition(db, user, collection, document_id, request, action):
    bill, correction = load(db, user, collection, document_id, lock=True)
    if correction is None:
        raise error("correction_not_saved", "Save and preview the correction before submitting or approving it.")
    if action in {"approve", "return"} and user.role not in {UserRole.ADMIN, UserRole.MANAGER}:
        raise error("approval_required", "Only Manager or Admin can approve or return corrections.", 403)
    require_version(correction.version, request.expected_version)
    if correction.status == "confirmed":
        if action == "approve" and bill.version == correction.version + 1:
            return read_original(collection, bill)
        raise error("version_conflict", "This correction has already been confirmed. Reopen the bill for a new correction.")
    ensure_eligible(db, bill)
    require_base(bill, correction)
    if action == "submit":
        if correction.status not in {"draft", "pending_approval"}:
            raise error("correction_not_editable", "Only saved draft corrections may be submitted.")
        if correction.status == "pending_approval":
            return read_view(collection, bill, correction, user)
        correction.status = "pending_approval"
        correction.submitted_by_id = user.id
        submitted = deepcopy(correction.working_snapshot)
        submitted["document"]["submitted_at"] = datetime.now(UTC).isoformat()
        correction.working_snapshot = submitted
    elif action == "return":
        if correction.status != "pending_approval" or not request.reason.strip():
            raise error("correction_return_reason", "A submitted correction and a return reason are required.", 422)
        correction.status = "draft"
        correction.version += 1
    else:
        if correction.status != "pending_approval":
            raise error("correction_not_submitted", "Submit this exact correction revision before approval.")
        if user.role != UserRole.ADMIN and user.id in {correction.created_by_id, correction.submitted_by_id}:
            raise error("independent_approval_required", "Independent approval is required; the correction creator or submitter cannot approve it.", 403)
        publish(db, user, collection, bill, correction)
    if action != "approve":
        staged = deepcopy(correction.working_snapshot)
        staged["document"].update(status=correction.status, version=correction.version, submitted_by_id=correction.submitted_by_id, submitted_revision=correction.version if correction.status == "pending_approval" else None)
        correction.working_snapshot = staged
    record_audit(db, user, collection, bill, "confirmed" if action == "approve" else "submitted" if action == "submit" else "returned", request.reason.strip() or correction.reason, correction.original_snapshot, snapshot(bill) if action == "approve" else correction.working_snapshot)
    db.commit()
    return read_original(collection, bill) if action == "approve" else read_view(collection, bill, correction, user)


def publish(db, user, collection, bill, correction):
    model, line_model, _, _ = domain(collection)
    candidate = restore(collection, correction.working_snapshot)
    # Approval publishes the already-calculated exact reviewed snapshot; it does
    # not refresh masters or recalculate with different precision/defaults.
    protected = {"id", "version", "status", "created_by_id", "created_at", "updated_at", "approved_revision", "submitted_revision", "submitted_by_id", "approved_by_id", "submitted_at", "approved_at", *PDF_FIELDS}
    for column in model.__table__.columns:
        if column.key not in protected:
            setattr(bill, column.key, deepcopy(getattr(candidate, column.key)))
    foreign_key = "invoice_id" if collection == "invoices" else "purchase_order_id"
    bill.lines = [line_model(**{column.key: deepcopy(getattr(line, column.key)) for column in line_model.__table__.columns if column.key not in {"id", foreign_key}}) for line in candidate.lines]
    bill.version = correction.version + 1
    bill.status = InvoiceStatus.APPROVED if collection == "invoices" else "approved"
    bill.approved_revision = bill.submitted_revision = correction.version
    bill.submitted_by_id = correction.submitted_by_id
    bill.submitted_at = candidate.submitted_at
    bill.approved_by_id = user.id
    bill.approved_at = datetime.now(UTC)
    for field in PDF_FIELDS:
        setattr(bill, field, None)
    correction.status = "confirmed"
    correction.approved_by_id = user.id
    # Resolve new line IDs/defaults inside this transaction before archiving the
    # exact published revision. A failure still rolls back the parent and stage.
    db.flush()
    history = InvoiceRevision if collection == "invoices" else PurchaseOrderRevision
    archive = deepcopy(correction.original_snapshot)
    archive["after"] = snapshot(bill)
    db.add(history(**{foreign_key: bill.id}, revision=bill.version, event="correction_confirmed", actor_user_id=user.id, reason=correction.reason, snapshot=archive))
