from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from io import StringIO
import csv
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import false, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, require_roles, resolve_branch_for_user
from app.db.session import get_db
from app.models.enums import InvoiceStatus, UserRole
from app.models.invoice import Invoice
from app.models.master_records import Customer
from app.models.payment import CreditLimitOverride, CustomerCreditLimit, PaymentAuditLog, PaymentIdempotency, Receipt, ReceiptAllocation
from app.models.user import User
from app.schemas.payments import AllocationCreate, AllocationRead, CreditLimitUpsert, CreditOverrideCreate, Page, ReceiptCreate, ReceiptRead, ReversalCreate, StatementItem
from app.services.idempotency import canonical_payload_hash, normalize_idempotency_key

router = APIRouter()
MONEY_ZERO = Decimal("0.00")


def _key(value: str | None) -> str:
    try:
        normalized = normalize_idempotency_key(value)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if normalized is None:
        raise HTTPException(422, "Idempotency-Key is required for payment writes")
    return normalized


def _customer(db: Session, user: User, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(404, "Customer not found")
    ensure_branch_access(user, customer.branch_id)
    if not customer.is_active:
        raise HTTPException(422, "Customer is inactive")
    return customer


def _scoped_statement(statement, model, user: User):
    if user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(user)
        statement = statement.where(model.branch_id.in_(assigned) if assigned else false())
    return statement


def _active_allocated(db: Session, receipt_id: int | None = None, invoice_id: int | None = None) -> Decimal:
    statement = select(func.coalesce(func.sum(ReceiptAllocation.amount), 0)).where(ReceiptAllocation.reversed_at.is_(None))
    if receipt_id is not None:
        statement = statement.where(ReceiptAllocation.receipt_id == receipt_id)
    if invoice_id is not None:
        statement = statement.where(ReceiptAllocation.invoice_id == invoice_id)
    return Decimal(db.scalar(statement) or MONEY_ZERO)


def _receipt_read(db: Session, receipt: Receipt) -> ReceiptRead:
    allocated = MONEY_ZERO if receipt.status == "reversed" else _active_allocated(db, receipt_id=receipt.id)
    return ReceiptRead(
        id=receipt.id, branch_id=receipt.branch_id, customer_id=receipt.customer_id,
        receipt_number=receipt.receipt_number, receipt_date=receipt.receipt_date, currency=receipt.currency,
        amount=receipt.amount, allocated_amount=allocated, unallocated_amount=receipt.amount - allocated,
        reference=receipt.reference, notes=receipt.notes, status=receipt.status, version=receipt.version,
        created_at=receipt.created_at,
    )


def _audit(db: Session, user: User, entity_type: str, entity_id: int, action: str, reason: str | None, before: dict | None, after: dict | None) -> None:
    db.add(PaymentAuditLog(actor_user_id=user.id, entity_type=entity_type, entity_id=entity_id, action=action, reason=reason, before=before, after=after))


def _idempotency_existing(db: Session, branch_id: int, operation: str, key: str, payload_hash: str):
    existing = db.scalar(select(PaymentIdempotency).where(PaymentIdempotency.branch_id == branch_id, PaymentIdempotency.operation == operation, PaymentIdempotency.idempotency_key == key))
    if existing is None:
        return None
    if existing.payload_hash != payload_hash:
        raise HTTPException(409, "Idempotency-Key was already used with a different payload")
    if operation == "receipt" and existing.receipt_id:
        return db.get(Receipt, existing.receipt_id)
    if operation == "allocation" and existing.allocation_id:
        return db.get(ReceiptAllocation, existing.allocation_id)
    raise HTTPException(409, "Payment request is still being finalized; retry the same request")


@router.post("/receipts", response_model=ReceiptRead, status_code=201)
def create_receipt(
    request: ReceiptCreate,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> ReceiptRead:
    customer = _customer(db, user, request.customer_id)
    branch = resolve_branch_for_user(db, user, customer.branch_id)
    key = _key(idempotency_key)
    payload_hash = canonical_payload_hash(request)
    existing = _idempotency_existing(db, branch.id, "receipt", key, payload_hash)
    if existing is not None:
        return _receipt_read(db, existing)
    record = PaymentIdempotency(branch_id=branch.id, operation="receipt", idempotency_key=key, payload_hash=payload_hash)
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = _idempotency_existing(db, branch.id, "receipt", key, payload_hash)
        if existing is None:
            raise HTTPException(409, "Payment request is being finalized; retry the same request") from None
        return _receipt_read(db, existing)
    receipt = Receipt(branch_id=branch.id, customer_id=customer.id, created_by_id=user.id, receipt_number="pending", receipt_date=request.receipt_date, currency=request.currency, amount=request.amount, reference=request.reference, notes=request.notes)
    db.add(receipt)
    db.flush()
    fy = f"{receipt.receipt_date.year if receipt.receipt_date.month >= 4 else receipt.receipt_date.year - 1}-{str((receipt.receipt_date.year if receipt.receipt_date.month >= 4 else receipt.receipt_date.year - 1) + 1)[-2:]}"
    receipt.receipt_number = f"RCPT/{fy}/NO. {receipt.id}"
    record.receipt_id = receipt.id
    _audit(db, user, "receipt", receipt.id, "created", None, None, {"amount": str(receipt.amount), "currency": receipt.currency})
    db.commit()
    db.refresh(receipt)
    response.headers["X-Idempotent-Replay"] = "false"
    return _receipt_read(db, receipt)


@router.get("/receipts", response_model=Page)
def list_receipts(
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), q: str | None = None,
    customer_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_active_user),
) -> Page:
    statement = _scoped_statement(select(Receipt), Receipt, user)
    if customer_id is not None:
        customer = _customer(db, user, customer_id)
        statement = statement.where(Receipt.customer_id == customer.id)
    if q and q.strip():
        statement = statement.where(Receipt.receipt_number.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(statement.order_by(Receipt.receipt_date.desc(), Receipt.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[_receipt_read(db, item) for item in items], total=total, page=page, page_size=page_size)


@router.post("/allocations", response_model=AllocationRead, status_code=201)
def allocate_receipt(
    request: AllocationCreate,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_active_user),
) -> AllocationRead:
    receipt = db.scalar(select(Receipt).where(Receipt.id == request.receipt_id).with_for_update())
    invoice = db.scalar(select(Invoice).where(Invoice.id == request.invoice_id).with_for_update())
    if receipt is None or invoice is None:
        raise HTTPException(404, "Receipt or invoice not found")
    ensure_branch_access(user, receipt.branch_id)
    if invoice.branch_id != receipt.branch_id or invoice.buyer_customer_id != receipt.customer_id:
        raise HTTPException(422, "Receipt customer and invoice do not match")
    if receipt.status != "posted":
        raise HTTPException(422, "Reversed receipt cannot be allocated")
    if invoice.status not in {InvoiceStatus.APPROVED, InvoiceStatus.PDF_GENERATED}:
        raise HTTPException(422, "Only approved invoices can receive allocations")
    if invoice.currency != receipt.currency:
        raise HTTPException(422, "Receipt and invoice currencies must match")
    key = _key(idempotency_key)
    payload_hash = canonical_payload_hash(request)
    existing = _idempotency_existing(db, receipt.branch_id, "allocation", key, payload_hash)
    if existing is not None:
        return AllocationRead.model_validate(existing, from_attributes=True)
    available_receipt = receipt.amount - _active_allocated(db, receipt_id=receipt.id)
    available_invoice = Decimal(invoice.final_total) - _active_allocated(db, invoice_id=invoice.id)
    if request.amount > available_receipt:
        raise HTTPException(422, f"Allocation exceeds unallocated receipt credit ({available_receipt})")
    if request.amount > available_invoice:
        raise HTTPException(422, f"Allocation exceeds invoice outstanding amount ({available_invoice})")
    record = PaymentIdempotency(branch_id=receipt.branch_id, operation="allocation", idempotency_key=key, payload_hash=payload_hash)
    allocation = ReceiptAllocation(receipt_id=receipt.id, invoice_id=invoice.id, created_by_id=user.id, amount=request.amount, currency=receipt.currency)
    db.add_all([record, allocation])
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = _idempotency_existing(db, receipt.branch_id, "allocation", key, payload_hash)
        if existing is None:
            raise HTTPException(409, "Allocation request is being finalized; retry the same request") from None
        return AllocationRead.model_validate(existing, from_attributes=True)
    record.allocation_id = allocation.id
    receipt.version += 1
    _audit(db, user, "allocation", allocation.id, "created", None, None, {"amount": str(allocation.amount), "invoice_id": invoice.id})
    db.commit()
    db.refresh(allocation)
    return AllocationRead.model_validate(allocation, from_attributes=True)


@router.post("/allocations/{allocation_id}/reverse", response_model=AllocationRead)
def reverse_allocation(allocation_id: int, request: ReversalCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)) -> AllocationRead:
    allocation = db.scalar(select(ReceiptAllocation).where(ReceiptAllocation.id == allocation_id).with_for_update())
    if allocation is None:
        raise HTTPException(404, "Allocation not found")
    receipt = db.scalar(select(Receipt).where(Receipt.id == allocation.receipt_id).with_for_update())
    ensure_branch_access(user, receipt.branch_id)
    if allocation.reversed_at is not None:
        raise HTTPException(409, "Allocation is already reversed")
    before = {"amount": str(allocation.amount), "invoice_id": allocation.invoice_id}
    allocation.reversed_at = datetime.now(UTC)
    allocation.reversed_by_id = user.id
    allocation.reversal_reason = request.reason
    receipt.version += 1
    _audit(db, user, "allocation", allocation.id, "reversed", request.reason, before, {"reversed_at": allocation.reversed_at.isoformat()})
    db.commit()
    db.refresh(allocation)
    return AllocationRead.model_validate(allocation, from_attributes=True)


@router.post("/receipts/{receipt_id}/reverse", response_model=ReceiptRead)
def reverse_receipt(receipt_id: int, request: ReversalCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)) -> ReceiptRead:
    receipt = db.scalar(select(Receipt).where(Receipt.id == receipt_id).with_for_update())
    if receipt is None:
        raise HTTPException(404, "Receipt not found")
    ensure_branch_access(user, receipt.branch_id)
    if receipt.status == "reversed":
        raise HTTPException(409, "Receipt is already reversed")
    now = datetime.now(UTC)
    for allocation in db.scalars(select(ReceiptAllocation).where(ReceiptAllocation.receipt_id == receipt.id, ReceiptAllocation.reversed_at.is_(None)).with_for_update()).all():
        allocation.reversed_at = now
        allocation.reversed_by_id = user.id
        allocation.reversal_reason = request.reason
        _audit(db, user, "allocation", allocation.id, "reversed_with_receipt", request.reason, {"amount": str(allocation.amount)}, {"reversed_at": now.isoformat()})
    receipt.status = "reversed"
    receipt.reversed_at = now
    receipt.reversed_by_id = user.id
    receipt.reversal_reason = request.reason
    receipt.version += 1
    _audit(db, user, "receipt", receipt.id, "reversed", request.reason, {"status": "posted"}, {"status": "reversed"})
    db.commit()
    db.refresh(receipt)
    return _receipt_read(db, receipt)


def _statement_rows(db: Session, user: User, customer_id: int) -> list[StatementItem]:
    customer = _customer(db, user, customer_id)
    invoices = db.scalars(_scoped_statement(select(Invoice).where(Invoice.buyer_customer_id == customer.id, Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.PDF_GENERATED])), Invoice, user).order_by(Invoice.invoice_date, Invoice.id)).all()
    today = date.today()
    result = []
    for invoice in invoices:
        allocated = _active_allocated(db, invoice_id=invoice.id)
        outstanding = max(Decimal(invoice.final_total) - allocated, MONEY_ZERO)
        overdue = max((today - invoice.due_date).days, 0) if invoice.due_date and outstanding > 0 else 0
        result.append(StatementItem(invoice_id=invoice.id, invoice_number=invoice.invoice_number, invoice_date=invoice.invoice_date, due_date=invoice.due_date, currency=invoice.currency, invoice_total=invoice.final_total, allocated_amount=allocated, outstanding_amount=outstanding, overdue_days=overdue))
    return result


@router.get("/customers/{customer_id}/statement", response_model=Page)
def customer_statement(customer_id: int, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(get_current_active_user)) -> Page:
    rows = _statement_rows(db, user, customer_id)
    return Page(items=rows[(page - 1) * page_size:page * page_size], total=len(rows), page=page, page_size=page_size)


@router.get("/customers/{customer_id}/ageing")
def customer_ageing(customer_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)) -> dict:
    rows = _statement_rows(db, user, customer_id)
    buckets = {"current": MONEY_ZERO, "1_30": MONEY_ZERO, "31_60": MONEY_ZERO, "61_90": MONEY_ZERO, "90_plus": MONEY_ZERO}
    for row in rows:
        if row.outstanding_amount <= 0:
            continue
        if row.overdue_days == 0: bucket = "current"
        elif row.overdue_days <= 30: bucket = "1_30"
        elif row.overdue_days <= 60: bucket = "31_60"
        elif row.overdue_days <= 90: bucket = "61_90"
        else: bucket = "90_plus"
        buckets[bucket] += row.outstanding_amount
    currencies = {row.currency for row in rows}
    return {"customer_id": customer_id, "currency": currencies.pop() if len(currencies) == 1 else "MIXED", "buckets": {key: str(value) for key, value in buckets.items()}, "total_outstanding": str(sum(buckets.values(), MONEY_ZERO))}


@router.get("/customers/{customer_id}/statement.csv")
def export_statement(customer_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))) -> StreamingResponse:
    rows = _statement_rows(db, user, customer_id)
    stream = StringIO()
    writer = csv.writer(stream)
    writer.writerow(["Invoice", "Invoice date", "Due date", "Currency", "Invoice total", "Allocated", "Outstanding", "Overdue days"])
    for row in rows:
        writer.writerow([row.invoice_number or row.invoice_id, row.invoice_date, row.due_date or "", row.currency, row.invoice_total, row.allocated_amount, row.outstanding_amount, row.overdue_days])
    return StreamingResponse(iter([stream.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=customer-{customer_id}-statement.csv"})


@router.get("/reconciliation", response_model=Page)
def reconciliation(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))) -> Page:
    statement = select(ReceiptAllocation).join(Receipt).where(ReceiptAllocation.reversed_at.is_(None))
    if user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(user)
        statement = statement.where(Receipt.branch_id.in_(assigned) if assigned else false())
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(statement.order_by(ReceiptAllocation.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[AllocationRead.model_validate(item, from_attributes=True) for item in items], total=total, page=page, page_size=page_size)


@router.put("/credit-limits/{customer_id}")
def upsert_credit_limit(customer_id: int, request: CreditLimitUpsert, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ADMIN))) -> dict:
    customer = _customer(db, user, customer_id)
    limit = db.scalar(select(CustomerCreditLimit).where(CustomerCreditLimit.customer_id == customer.id, CustomerCreditLimit.branch_id == customer.branch_id).with_for_update())
    before = {"limit_amount": str(limit.limit_amount), "currency": limit.currency} if limit else None
    if limit is None:
        limit = CustomerCreditLimit(branch_id=customer.branch_id, customer_id=customer.id, currency=request.currency, limit_amount=request.limit_amount, is_active=request.is_active)
        db.add(limit)
    else:
        limit.currency, limit.limit_amount, limit.is_active = request.currency, request.limit_amount, request.is_active
    db.flush()
    _audit(db, user, "credit_limit", limit.id, "upserted", None, before, {"limit_amount": str(limit.limit_amount), "currency": limit.currency, "is_active": limit.is_active})
    db.commit()
    return {"customer_id": customer.id, "currency": limit.currency, "limit_amount": str(limit.limit_amount), "is_active": limit.is_active}


@router.get("/credit-limits/{customer_id}")
def get_credit_limit(customer_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)) -> dict:
    customer = _customer(db, user, customer_id)
    limit = db.scalar(select(CustomerCreditLimit).where(CustomerCreditLimit.customer_id == customer.id, CustomerCreditLimit.branch_id == customer.branch_id))
    if limit is None:
        return {"customer_id": customer.id, "configured": False}
    return {"customer_id": customer.id, "configured": True, "currency": limit.currency, "limit_amount": str(limit.limit_amount), "is_active": limit.is_active}


@router.post("/credit-limits/{customer_id}/override")
def create_credit_override(customer_id: int, request: CreditOverrideCreate, db: Session = Depends(get_db), user: User = Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))) -> dict:
    customer = _customer(db, user, customer_id)
    record = CreditLimitOverride(branch_id=customer.branch_id, customer_id=customer.id, actor_user_id=user.id, currency=request.currency, amount=request.amount, reason=request.reason)
    db.add(record)
    db.flush()
    _audit(db, user, "credit_limit", customer.id, "override_created", request.reason, None, {"amount": str(request.amount), "currency": request.currency, "override_id": record.id})
    db.commit()
    return {"id": record.id, "customer_id": record.customer_id, "amount": str(record.amount), "currency": record.currency, "reason": record.reason, "created_at": record.created_at}
