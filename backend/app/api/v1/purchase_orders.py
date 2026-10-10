from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import false, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, require_roles, resolve_branch_for_user
from app.api.v1.invoices import financial_year_for, _line_to_calculation as reagent_line_to_calculation, _manual_product_for_preview
from app.core.config import get_settings
from app.db.session import get_db
from app.models.company import Branch, Company
from app.models.enums import UserRole
from app.models.master_records import BankAccount, Product, Purchaser, Supplier, TermsAndConditions
from app.models.purchase_order import PurchaseOrder, PurchaseOrderAuditLog, PurchaseOrderCreationRequest, PurchaseOrderLine, PurchaseOrderRevision
from app.models.user import User
from app.schemas.common import BillDeleteRequest
from app.schemas.invoice import InvoiceLineInput, InvoicePreviewRead, PdfPreviewRequest
from app.schemas.master_records import PurchaserCreate, SupplierCreate
from app.schemas.purchase_order import PurchaseOrderCreate, PurchaseOrderReasonAction, PurchaseOrderRead, PurchaseOrderRegisterPage, PurchaseOrderUpdate, PurchaseOrderWorkflowAction
from app.services.invoice_calculator import InvoiceCalculationLine, calculate_invoice
from app.services.invoice_pdf import PdfLayoutError, build_purchase_order_context, build_reagent_purchase_order_context, render_invoice_pdf
from app.services.financial_validation import FinancialValidationError
from app.services.idempotency import canonical_payload_hash, normalize_idempotency_key
from app.services.billing_addresses import company_address_snapshot, postal_address_lines
from app.services.bill_deletion import delete_bill


router = APIRouter()

# Kept as a document-specific seam so tests and future purchase-order template
# changes do not need to know that Playwright is shared with invoice PDFs.
render_purchase_order_pdf = render_invoice_pdf

REAGENT_METADATA = (
    "place_of_supply_state_code", "delivery_note_date", "po_reference_number",
    "po_reference_date", "transport_mode", "vehicle_number", "vehicle_type", "lr_number", "lr_date",
)


def _clear_pdf_reference(purchase_order: PurchaseOrder) -> None:
    # Keep the old file for history, but never serve it as the amended revision.
    for field in ("pdf_sha256", "pdf_template_version", "pdf_storage_key", "pdf_generated_by_id", "pdf_generated_at"):
        setattr(purchase_order, field, None)


def _set_reagent_details(purchase_order: PurchaseOrder, request: PurchaseOrderCreate) -> None:
    if request.document_type != "reagent":
        return
    for field in REAGENT_METADATA:
        setattr(purchase_order, field, getattr(request, field))
    purchase_order.consignee_details = request.consignee.model_dump(mode="json") if request.consignee else None


def _calculate_purchase_order(db: Session, branch: Branch, request: PurchaseOrderCreate, supplier_state: str, *, persist: bool):
    _ensure_no_purchase_order_discounts(request)
    if request.document_type == "reagent":
        prepared = [reagent_line_to_calculation(db, branch.id, line, persist_manual_products=persist, require_manufacturer=True) for line in request.lines]
    else:
        prepared = [_line_to_calculation(db, branch.id, line, persist_manual_products=persist) for line in request.lines]
    try:
        calculation = calculate_invoice(
            branch_state_code=branch.state_code,
            place_of_supply_state_code=request.place_of_supply_state_code if request.document_type == "reagent" else supplier_state,
            lines=[line for _, line in prepared],
            freight_charges=request.freight_charges, packing_charges=request.packing_charges,
            other_charges=request.other_charges, discount_amount=request.discount_amount,
        )
    except FinancialValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [product for product, _ in prepared], calculation


@router.post("/preview", response_model=InvoicePreviewRead)
def preview_purchase_order(
    request: PurchaseOrderCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    branch = resolve_branch_for_user(db, current_user, request.branch_id)
    # Preview must never create a supplier, purchaser or product master.
    if request.supplier_id is not None:
        supplier = _resolve_supplier(db, branch.id, request.supplier_id, request.supplier)
        supplier_state = request.supplier.address.state_code if request.supplier else supplier.state_code
    elif request.supplier is not None and request.supplier.is_active:
        if request.supplier.branch_id not in (None, branch.id):
            raise HTTPException(status_code=422, detail="Supplier seller profile does not match")
        supplier_state = request.supplier.address.state_code
    else:
        raise HTTPException(status_code=422, detail="Active supplier details are required")
    _resolve_purchaser(db, branch.id, request.purchaser_id, request.purchaser, False)
    _, calculation = _calculate_purchase_order(db, branch, request, supplier_state, persist=False)
    return InvoicePreviewRead.model_validate(calculation, from_attributes=True)


def _idempotency_key_or_422(value: str | None) -> str | None:
    try:
        return normalize_idempotency_key(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


def _purchase_order_for_creation_request(db: Session, request: PurchaseOrderCreationRequest) -> PurchaseOrder:
    if request.deleted_at is not None:
        raise HTTPException(status_code=410, detail={"code": "bill_deleted", "message": "This bill was permanently deleted. Start a new bill to reuse its number; the old save request cannot recreate it."})
    if request.purchase_order_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Purchase-order creation is still being finalized; retry the same request")
    purchase_order = db.scalar(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.lines))
        .where(PurchaseOrder.id == request.purchase_order_id)
    )
    if purchase_order is None:
        if db.scalar(select(PurchaseOrderCreationRequest.deleted_at).where(PurchaseOrderCreationRequest.id == request.id)) is not None:
            raise HTTPException(status_code=410, detail={"code": "bill_deleted", "message": "This bill was permanently deleted. Start a new bill to reuse its number; the old save request cannot recreate it."})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Stored purchase-order idempotency record is invalid")
    return purchase_order


def _claim_purchase_order_creation(
    db: Session,
    branch_id: int,
    idempotency_key: str | None,
    payload_hash: str,
) -> tuple[PurchaseOrderCreationRequest | None, PurchaseOrder | None]:
    if idempotency_key is None:
        return None, None
    creation_request = PurchaseOrderCreationRequest(
        branch_id=branch_id,
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
    )
    db.add(creation_request)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(PurchaseOrderCreationRequest).where(
                PurchaseOrderCreationRequest.branch_id == branch_id,
                PurchaseOrderCreationRequest.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key is being finalized; retry the same request") from None
        if existing.payload_hash != payload_hash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key was already used with a different payload")
        return None, _purchase_order_for_creation_request(db, existing)
    return creation_request, None


def _required_manual_line_value(line: InvoiceLineInput, field: str):
    value = getattr(line, field)
    if value is None or value == "":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Manual product line requires {field}",
        )
    return value


def _ensure_no_purchase_order_discounts(request: PurchaseOrderCreate) -> None:
    if request.document_type == "reagent":
        return
    if request.discount_amount != Decimal("0.00") or any(
        line.discount_amount != Decimal("0.00") or line.discount_percent != Decimal("0.00") for line in request.lines
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Discounts are not supported on purchase orders",
        )


def _get_or_create_product_from_manual(db: Session, branch_id: int, line: InvoiceLineInput) -> Product:
    product_name = _required_manual_line_value(line, "product_name").strip()
    hsn_sac = _required_manual_line_value(line, "hsn_sac").strip()
    unit = _required_manual_line_value(line, "unit").strip()
    rate = _required_manual_line_value(line, "rate")
    gst_rate = _required_manual_line_value(line, "gst_rate")
    cess_rate = line.cess_rate if line.cess_rate is not None else Decimal("0.00")

    existing = db.scalar(
        select(Product)
        .where(
            Product.branch_id == branch_id,
            func.lower(Product.name) == product_name.lower(),
            Product.hsn_sac == hsn_sac,
            Product.unit == unit,
            Product.is_active.is_(True),
        )
        .order_by(Product.id)
    )
    if existing is not None:
        return existing

    product = Product(
        branch_id=branch_id,
        name=product_name,
        description=line.description,
        hsn_sac=hsn_sac,
        unit=unit,
        base_rate=rate,
        gst_rate=gst_rate,
        cess_rate=cess_rate,
        is_active=True,
    )
    db.add(product)
    db.flush()
    return product


def _line_to_calculation(db: Session, branch_id: int, line: InvoiceLineInput, *, persist_manual_products: bool = True) -> tuple[Product, InvoiceCalculationLine]:
    if line.product_id is not None:
        product = db.get(Product, line.product_id)
        if product is None or product.branch_id != branch_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Product does not exist for this branch")
        if not product.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Product is inactive")
    else:
        product = _get_or_create_product_from_manual(db, branch_id, line) if persist_manual_products else _manual_product_for_preview(branch_id, line, None)
    return (
        product,
        InvoiceCalculationLine(
            description=line.description or product.description or product.name,
            hsn_sac=line.hsn_sac or product.hsn_sac,
            quantity=line.quantity,
            unit=line.unit or product.unit,
            rate=line.rate if line.rate is not None else product.base_rate,
            other_charge=line.other_charge,
            discount_amount=line.discount_amount,
            gst_rate=line.gst_rate if line.gst_rate is not None else product.gst_rate,
            cess_rate=line.cess_rate if line.cess_rate is not None else product.cess_rate,
        ),
    )


def _supplier_from_inline(db: Session, branch_id: int, request: SupplierCreate) -> Supplier:
    if request.branch_id is not None and request.branch_id != branch_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Supplier branch must match purchase order branch",
        )
    if not request.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Inline supplier details cannot be inactive for a new transaction",
        )
    if request.gstin:
        existing = db.scalar(
            select(Supplier)
            .where(Supplier.branch_id == branch_id, Supplier.gstin == request.gstin, Supplier.is_active.is_(True))
            .order_by(Supplier.id)
        )
        if existing is not None:
            return existing
    existing_by_name = db.scalar(
        select(Supplier)
        .where(
            Supplier.branch_id == branch_id,
            func.lower(Supplier.name) == request.name.strip().lower(),
            Supplier.phone == request.phone,
            Supplier.is_active.is_(True),
        )
        .order_by(Supplier.id)
    )
    if existing_by_name is not None:
        return existing_by_name

    address = request.address
    supplier = Supplier(
        branch_id=branch_id,
        name=request.name,
        gstin=request.gstin,
        pan=request.pan,
        email=request.email,
        phone=request.phone,
        address_name=address.name,
        address_line1=address.address_line1,
        address_line2=address.address_line2,
        city=address.city,
        state=address.state,
        state_code=address.state_code,
        postal_code=address.postal_code,
        is_active=request.is_active,
    )
    db.add(supplier)
    db.flush()
    return supplier


def _resolve_supplier(db: Session, branch_id: int, supplier_id: int | None, inline_supplier: SupplierCreate | None) -> Supplier:
    if inline_supplier is not None:
        if inline_supplier.branch_id not in (None, branch_id):
            raise HTTPException(status_code=422, detail="Supplier seller profile does not match")
        if not inline_supplier.is_active:
            raise HTTPException(status_code=422, detail="Inline supplier details cannot be inactive for a new transaction")
    if supplier_id is not None:
        supplier = db.get(Supplier, supplier_id)
        if supplier is None or supplier.branch_id != branch_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Supplier does not exist for this branch")
        if not supplier.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Supplier is inactive")
        return supplier
    if inline_supplier is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Supplier or supplier details are required",
        )
    return _supplier_from_inline(db, branch_id, inline_supplier)


def _set_supplier_snapshot(
    purchase_order: PurchaseOrder,
    supplier: Supplier,
    inline_supplier: SupplierCreate | None = None,
) -> None:
    purchase_order.supplier_name = inline_supplier.name if inline_supplier else supplier.name
    purchase_order.supplier_gstin = inline_supplier.gstin if inline_supplier else supplier.gstin
    purchase_order.supplier_pan = inline_supplier.pan if inline_supplier else supplier.pan
    purchase_order.supplier_email = inline_supplier.email if inline_supplier else supplier.email
    purchase_order.supplier_phone = inline_supplier.phone if inline_supplier else supplier.phone
    if inline_supplier:
        address = inline_supplier.address
        purchase_order.supplier_address_line1 = address.address_line1
        purchase_order.supplier_address_line2 = address.address_line2
        purchase_order.supplier_city = address.city
        purchase_order.supplier_state = address.state
        purchase_order.supplier_state_code = address.state_code
        purchase_order.supplier_postal_code = address.postal_code
    else:
        purchase_order.supplier_address_line1 = supplier.address_line1
        purchase_order.supplier_address_line2 = supplier.address_line2
        purchase_order.supplier_city = supplier.city
        purchase_order.supplier_state = supplier.state
        purchase_order.supplier_state_code = supplier.state_code
        purchase_order.supplier_postal_code = supplier.postal_code
    if purchase_order.company_registered_address is not None:
        purchase_order.pickup_address = ", ".join(postal_address_lines(purchase_order, prefix="supplier_"))


def _purchaser_from_inline(db: Session, branch_id: int, request: PurchaserCreate) -> Purchaser:
    if request.branch_id is not None and request.branch_id != branch_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Purchaser branch must match purchase order branch",
        )
    if not request.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Inline purchaser details cannot be inactive for a new transaction",
        )

    if request.gstin:
        existing = db.scalar(
            select(Purchaser).where(
                Purchaser.branch_id == branch_id,
                Purchaser.gstin == request.gstin,
                Purchaser.is_active.is_(True),
            ).order_by(Purchaser.id)
        )
        if existing is not None:
            return existing
    existing_by_name = db.scalar(
        select(Purchaser).where(
            Purchaser.branch_id == branch_id,
            func.lower(Purchaser.name) == request.name.strip().lower(),
            Purchaser.phone == request.phone,
            Purchaser.is_active.is_(True),
        ).order_by(Purchaser.id)
    )
    if existing_by_name is not None:
        return existing_by_name

    address = request.address
    purchaser = Purchaser(
        branch_id=branch_id,
        name=request.name,
        gstin=request.gstin,
        pan=request.pan,
        email=request.email,
        phone=request.phone,
        address_name=address.name,
        address_line1=address.address_line1,
        address_line2=address.address_line2,
        city=address.city,
        state=address.state,
        state_code=address.state_code,
        postal_code=address.postal_code,
        is_active=True,
    )
    db.add(purchaser)
    db.flush()
    return purchaser


def _resolve_purchaser(
    db: Session,
    branch_id: int,
    purchaser_id: int | None,
    inline_purchaser: PurchaserCreate | None,
    save_for_future: bool,
) -> Purchaser | None:
    if purchaser_id is not None and inline_purchaser is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Choose a saved purchaser or enter purchaser details, not both",
        )
    if purchaser_id is not None:
        purchaser = db.get(Purchaser, purchaser_id)
        if purchaser is None or purchaser.branch_id != branch_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Purchaser does not exist for this seller profile",
            )
        if not purchaser.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Purchaser is inactive")
        return purchaser
    if inline_purchaser is None:
        # Purchaser entry is optional. Do not infer a second party or create
        # a master when the PO only contains seller/shipping details.
        return None
    if inline_purchaser.branch_id not in (None, branch_id):
        raise HTTPException(status_code=422, detail="Purchaser seller profile does not match")
    if not inline_purchaser.is_active:
        raise HTTPException(status_code=422, detail="Inline purchaser details cannot be inactive for a new transaction")
    return _purchaser_from_inline(db, branch_id, inline_purchaser) if save_for_future else None


def _set_purchaser_snapshot(
    purchase_order: PurchaseOrder,
    purchaser: Purchaser | None,
    inline_purchaser: PurchaserCreate | None = None,
) -> None:
    if inline_purchaser is not None:
        source = inline_purchaser
        address = source.address
        purchase_order.purchaser_name = source.name
        purchase_order.purchaser_gstin = source.gstin
        purchase_order.purchaser_pan = source.pan
        purchase_order.purchaser_email = source.email
        purchase_order.purchaser_phone = source.phone
        purchase_order.purchaser_address_line1 = address.address_line1
        purchase_order.purchaser_address_line2 = address.address_line2
        purchase_order.purchaser_city = address.city
        purchase_order.purchaser_state = address.state
        purchase_order.purchaser_state_code = address.state_code
        purchase_order.purchaser_postal_code = address.postal_code
    elif purchaser is not None:
        purchase_order.purchaser_name = purchaser.name
        purchase_order.purchaser_gstin = purchaser.gstin
        purchase_order.purchaser_pan = purchaser.pan
        purchase_order.purchaser_email = purchaser.email
        purchase_order.purchaser_phone = purchaser.phone
        purchase_order.purchaser_address_line1 = purchaser.address_line1
        purchase_order.purchaser_address_line2 = purchaser.address_line2
        purchase_order.purchaser_city = purchaser.city
        purchase_order.purchaser_state = purchaser.state
        purchase_order.purchaser_state_code = purchaser.state_code
        purchase_order.purchaser_postal_code = purchaser.postal_code
    else:
        for field in ("name", "gstin", "pan", "email", "phone", "address_line1", "address_line2", "city", "state", "state_code", "postal_code"):
            setattr(purchase_order, f"purchaser_{field}", None)


def _apply_calculation(purchase_order: PurchaseOrder, calculation) -> None:
    purchase_order.taxable_value = calculation.taxable_value
    purchase_order.cgst_amount = calculation.cgst_amount
    purchase_order.sgst_amount = calculation.sgst_amount
    purchase_order.igst_amount = calculation.igst_amount
    purchase_order.cess_amount = calculation.cess_amount
    purchase_order.unrounded_total = calculation.unrounded_total
    purchase_order.round_off = calculation.round_off
    purchase_order.final_total = calculation.final_total
    purchase_order.amount_in_words = calculation.amount_in_words


def _set_lines(purchase_order: PurchaseOrder, products: list[Product], calculation, product_names: list[str | None] | None = None) -> None:
    purchase_order.lines = [
        PurchaseOrderLine(
            product_id=product.id,
            sort_order=index + 1,
            product_name=(product_names[index] or product.name) if product_names is not None else product.name,
            manufacturer_name=line.manufacturer_name,
            manufacturer_code=line.manufacturer_code,
            manufacturer_product_code=line.manufacturer_product_code,
            part_no=line.part_no,
            pack_size=line.pack_size,
            discount_percent=line.discount_percent,
            description=line.description,
            hsn_sac=line.hsn_sac,
            quantity=line.quantity,
            unit=line.unit,
            rate=line.rate,
            other_charge=line.other_charge,
            discount_amount=line.discount_amount,
            taxable_value=line.taxable_value,
            gst_rate=line.gst_rate,
            cess_rate=line.cess_rate,
            cgst_amount=line.cgst_amount,
            sgst_amount=line.sgst_amount,
            igst_amount=line.igst_amount,
            cess_amount=line.cess_amount,
            line_total=line.line_total,
        )
        for index, (product, line) in enumerate(zip(products, calculation.lines, strict=True))
    ]


def _create_purchase_order_number(branch: Branch, purchase_order_id: int, order_date) -> str:
    return f"PO-{branch.gstin}/{financial_year_for(order_date)}/{purchase_order_id:05d}"


def _purchase_order_number_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"code": "duplicate_po_number", "field": "purchase_order_number", "message": "This PO No. is already in use. Enter a different number."},
    )


def _set_purchase_order_number(db: Session, purchase_order: PurchaseOrder, number: str) -> bool:
    # Canonicalize new numbers, but never rewrite an older stored identifier.
    if purchase_order.purchase_order_number.upper() == number.upper():
        return False
    if purchase_order.approved_at is not None:
        raise HTTPException(status_code=409, detail="An approved PO No. cannot be changed, including during an amendment")
    existing = select(PurchaseOrder.id).where(func.upper(PurchaseOrder.purchase_order_number) == number.upper())
    if purchase_order.id is not None:
        existing = existing.where(PurchaseOrder.id != purchase_order.id)
    if db.scalar(existing) is not None:
        raise _purchase_order_number_conflict()
    purchase_order.purchase_order_number = number
    try:
        # The existing database UNIQUE constraint is the concurrent-write backstop.
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if "purchase_order_number" in str(exc.orig):
            raise _purchase_order_number_conflict() from exc
        raise
    return True


def _pdf_storage_directory() -> Path:
    configured = Path(get_settings().pdf_storage_dir)
    return configured if configured.is_absolute() else Path.cwd() / configured


def _pdf_file_path(storage_key: str) -> Path:
    directory = _pdf_storage_directory().resolve()
    path = (directory / storage_key).resolve()
    if path.parent != directory:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid stored PDF path")
    return path


def _write_pdf_bytes(purchase_order: PurchaseOrder, pdf_bytes: bytes, sha256: str) -> str:
    directory = _pdf_storage_directory()
    directory.mkdir(parents=True, exist_ok=True)
    storage_key = f"purchase-order-{purchase_order.id}-{sha256[:16]}.pdf"
    final_path = directory / storage_key
    temporary_path = directory / f".{storage_key}.{uuid4().hex}.tmp"
    temporary_path.write_bytes(pdf_bytes)
    temporary_path.replace(final_path)
    return storage_key


def _get_purchase_order(
    db: Session,
    current_user: User,
    purchase_order_id: int,
    *,
    for_update: bool = False,
) -> PurchaseOrder:
    statement = select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)).where(PurchaseOrder.id == purchase_order_id)
    if for_update:
        statement = statement.with_for_update()
    purchase_order = db.scalar(statement)
    if purchase_order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    ensure_branch_access(current_user, purchase_order.branch_id)
    return purchase_order


def _version_conflict(purchase_order: PurchaseOrder) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "version_conflict",
            "message": "This purchase order was changed by another user. Reload it before saving.",
            "current_version": purchase_order.version,
        },
    )


def _require_version(purchase_order: PurchaseOrder, expected_version: int | None) -> None:
    if purchase_order.document_type == "reagent" and expected_version is None:
        raise HTTPException(status_code=422, detail="expected_version is required for reagent purchase-order changes")
    if expected_version is not None and expected_version != purchase_order.version:
        raise _version_conflict(purchase_order)


def _revision_snapshot(purchase_order: PurchaseOrder) -> dict:
    def serialized(value):
        if isinstance(value, Decimal):
            return str(value)
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value
    full_snapshot = {
        "document": {column.name: serialized(getattr(purchase_order, column.name)) for column in PurchaseOrder.__table__.columns},
        "lines": [{column.name: serialized(getattr(line, column.name)) for column in PurchaseOrderLine.__table__.columns} for line in purchase_order.lines],
    }
    if purchase_order.document_type == "reagent":
        return full_snapshot
    return {
        "document": full_snapshot["document"],
        "document_type": purchase_order.document_type,
        "consignee": purchase_order.consignee_details,
        "transport": {field: str(getattr(purchase_order, field)) if getattr(purchase_order, field) is not None else None for field in REAGENT_METADATA},
        "purchase_order_number": purchase_order.purchase_order_number,
        "order_date": purchase_order.order_date.isoformat(),
        "supplier": {"name": purchase_order.supplier_name, "gstin": purchase_order.supplier_gstin, "address_line1": purchase_order.supplier_address_line1, "city": purchase_order.supplier_city, "state": purchase_order.supplier_state, "state_code": purchase_order.supplier_state_code, "postal_code": purchase_order.supplier_postal_code},
        "purchaser": {"name": purchase_order.purchaser_name, "gstin": purchase_order.purchaser_gstin, "address_line1": purchase_order.purchaser_address_line1, "city": purchase_order.purchaser_city, "state": purchase_order.purchaser_state, "state_code": purchase_order.purchaser_state_code, "postal_code": purchase_order.purchaser_postal_code},
        "totals": {"taxable_value": str(purchase_order.taxable_value), "cgst_amount": str(purchase_order.cgst_amount), "sgst_amount": str(purchase_order.sgst_amount), "igst_amount": str(purchase_order.igst_amount), "cess_amount": str(purchase_order.cess_amount), "final_total": str(purchase_order.final_total)},
        "lines": full_snapshot["lines"],
    }


def _record_revision(db: Session, purchase_order: PurchaseOrder, current_user: User, event: str, reason: str | None = None) -> None:
    db.add(PurchaseOrderRevision(purchase_order_id=purchase_order.id, revision=purchase_order.version, event=event, actor_user_id=current_user.id, reason=reason, snapshot=_revision_snapshot(purchase_order)))


def _record_transition(db: Session, purchase_order: PurchaseOrder, current_user: User, to_status: str, note: str | None = None) -> None:
    from_status = purchase_order.status
    if from_status == to_status:
        return
    purchase_order.status = to_status
    timestamp = datetime.now(UTC)
    if to_status == "pending_approval":
        purchase_order.submitted_by_id = current_user.id
        purchase_order.submitted_at = timestamp
        purchase_order.submitted_revision = purchase_order.version
    elif to_status == "approved":
        purchase_order.approved_by_id = current_user.id
        purchase_order.approved_at = timestamp
        purchase_order.approved_revision = purchase_order.version
    elif to_status == "closed":
        purchase_order.closed_at = timestamp
    db.add(PurchaseOrderAuditLog(purchase_order_id=purchase_order.id, from_status=from_status, to_status=to_status, actor_user_id=current_user.id, note=note))


def _purchase_order_pdf_context(db: Session, purchase_order: PurchaseOrder, generated_at: datetime):
    branch = db.get(Branch, purchase_order.branch_id)
    company = db.get(Company, branch.company_id) if branch else None
    bank_account = db.scalar(
        select(BankAccount)
        .where(
            BankAccount.branch_id == purchase_order.branch_id,
            BankAccount.is_active.is_(True),
            BankAccount.is_default.is_(True),
        )
        .order_by(BankAccount.id)
    )
    terms = db.scalar(
        select(TermsAndConditions)
        .where(
            TermsAndConditions.branch_id == purchase_order.branch_id,
            TermsAndConditions.is_active.is_(True),
            TermsAndConditions.is_default.is_(True),
        )
        .order_by(TermsAndConditions.id)
    )
    context_builder = build_reagent_purchase_order_context if purchase_order.document_type == "reagent" else build_purchase_order_context
    return context_builder(
        purchase_order,
        company=company,
        branch=branch,
        bank_account=bank_account,
        terms=terms,
        generated_at=generated_at,
    )


@router.post("/{purchase_order_id}/preview-pdf", response_class=Response)
def preview_purchase_order_pdf(
    purchase_order_id: int,
    request: PdfPreviewRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Response:
    purchase_order = _get_purchase_order(db, current_user, purchase_order_id, for_update=True)
    _require_version(purchase_order, request.expected_version)
    context = _purchase_order_pdf_context(db, purchase_order, datetime.now(UTC))
    try:
        result = render_purchase_order_pdf(context)
    except PdfLayoutError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(
        content=result.pdf_bytes,
        media_type="application/pdf",
        headers={"Cache-Control": "no-store", "Content-Disposition": f'inline; filename="purchase-order-{purchase_order.id}-preview.pdf"'},
    )


def _generate_purchase_order_pdf(db: Session, purchase_order: PurchaseOrder, current_user: User) -> PurchaseOrder:
    branch = db.get(Branch, purchase_order.branch_id)
    company = db.get(Company, branch.company_id) if branch else None
    bank_account = db.scalar(
        select(BankAccount)
        .where(
            BankAccount.branch_id == purchase_order.branch_id,
            BankAccount.is_active.is_(True),
            BankAccount.is_default.is_(True),
        )
        .order_by(BankAccount.id)
    )
    terms = db.scalar(
        select(TermsAndConditions)
        .where(
            TermsAndConditions.branch_id == purchase_order.branch_id,
            TermsAndConditions.is_active.is_(True),
            TermsAndConditions.is_default.is_(True),
        )
        .order_by(TermsAndConditions.id)
    )
    generated_at = datetime.now(UTC)
    context_builder = build_reagent_purchase_order_context if purchase_order.document_type == "reagent" else build_purchase_order_context
    context = context_builder(
        purchase_order,
        company=company,
        branch=branch,
        bank_account=bank_account,
        terms=terms,
        generated_at=generated_at,
    )
    try:
        result = render_purchase_order_pdf(context)
    except PdfLayoutError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    storage_key = _write_pdf_bytes(purchase_order, result.pdf_bytes, result.sha256)
    purchase_order.pdf_sha256 = result.sha256
    purchase_order.pdf_template_version = context.template_version
    purchase_order.pdf_storage_key = storage_key
    purchase_order.pdf_generated_by_id = current_user.id
    purchase_order.pdf_generated_at = generated_at
    return purchase_order


@router.post("", response_model=PurchaseOrderRead, status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    request: PurchaseOrderCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> PurchaseOrder:
    branch = resolve_branch_for_user(db, current_user, request.branch_id)
    _ensure_no_purchase_order_discounts(request)
    normalized_key = _idempotency_key_or_422(idempotency_key)
    # Keep pre-existing automatic-number save hashes stable. A supplied manual
    # number is part of the intended transaction and must affect the hash.
    hash_exclusions = {"lines": {index: {"pack_size"} for index, line in enumerate(request.lines) if line.pack_size is None}}
    if request.purchase_order_number is None:
        hash_exclusions["purchase_order_number"] = True
    payload_hash = canonical_payload_hash(request, exclude=hash_exclusions)
    if normalized_key is not None:
        existing_request = db.scalar(
            select(PurchaseOrderCreationRequest).where(
                PurchaseOrderCreationRequest.branch_id == branch.id,
                PurchaseOrderCreationRequest.idempotency_key == normalized_key,
            )
        )
        if existing_request is not None:
            if existing_request.payload_hash != payload_hash:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key was already used with a different payload")
            response.status_code = status.HTTP_200_OK
            return _purchase_order_for_creation_request(db, existing_request)

    try:
        creation_request, replay = _claim_purchase_order_creation(db, branch.id, normalized_key, payload_hash)
        if replay is not None:
            response.status_code = status.HTTP_200_OK
            return replay

        supplier = _resolve_supplier(db, branch.id, request.supplier_id, request.supplier)
        purchaser = _resolve_purchaser(
            db,
            branch.id,
            request.purchaser_id,
            request.purchaser,
            request.save_purchaser_for_future,
        )
        supplier_state = request.supplier.address.state_code if request.supplier else supplier.state_code
        products, calculation = _calculate_purchase_order(db, branch, request, supplier_state, persist=True)
        purchase_order = PurchaseOrder(
            branch_id=branch.id,
            supplier_id=supplier.id,
            purchaser_id=purchaser.id if purchaser is not None else None,
            created_by_id=current_user.id,
            purchase_order_number=f"PO-DRAFT-{uuid4().hex}",
            order_date=request.order_date,
            document_type=request.document_type,
            expected_delivery_date=request.expected_delivery_date,
            payment_terms=request.payment_terms,
            transport_mode=request.transport_mode,
            status="draft",
            branch_name=branch.name,
            branch_gstin=branch.gstin,
            branch_state_code=branch.state_code,
            supplier_name=supplier.name,
            supplier_gstin=supplier.gstin,
            supplier_pan=supplier.pan,
            supplier_email=supplier.email,
            supplier_phone=supplier.phone,
            supplier_address_line1=supplier.address_line1,
            supplier_address_line2=supplier.address_line2,
            supplier_city=supplier.city,
            supplier_state=supplier.state,
            supplier_state_code=supplier.state_code,
            supplier_postal_code=supplier.postal_code,
            freight_charges=request.freight_charges,
            packing_charges=request.packing_charges,
            other_charges=request.other_charges,
            discount_amount=request.discount_amount,
            amount_in_words="",
        )
        purchase_order.company_registered_address = company_address_snapshot(db.get(Company, branch.company_id), branch)
        purchase_order.seller_email_addresses = [email for email in (branch.email, branch.secondary_email) if email]
        _set_supplier_snapshot(purchase_order, supplier, request.supplier)
        _set_purchaser_snapshot(purchase_order, purchaser, request.purchaser)
        _set_reagent_details(purchase_order, request)
        db.add(purchase_order)
        db.flush()
        _set_purchase_order_number(
            db, purchase_order,
            request.purchase_order_number or _create_purchase_order_number(branch, purchase_order.id, request.order_date),
        )
        _set_lines(purchase_order, products, calculation)
        for stored, submitted in zip(purchase_order.lines, request.lines, strict=True):
            stored.manufacturer_id = submitted.manufacturer_id if request.document_type == "reagent" else None
        _apply_calculation(purchase_order, calculation)
        _record_revision(db, purchase_order, current_user, "created")
        if creation_request is not None:
            creation_request.purchase_order_id = purchase_order.id
        db.commit()
        db.refresh(purchase_order)
        return purchase_order
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.get("", response_model=list[PurchaseOrderRead])
def list_purchase_orders(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    branch_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    document_type: Literal["domestic_oils", "reagent"] = "domestic_oils",
) -> list[PurchaseOrder]:
    statement = select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)).where(PurchaseOrder.document_type == document_type).order_by(PurchaseOrder.id)
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
        statement = statement.where(PurchaseOrder.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(current_user)
        statement = statement.where(PurchaseOrder.branch_id.in_(assigned) if assigned else false())
    return list(db.scalars(statement.limit(limit)))


@router.get("/register", response_model=PurchaseOrderRegisterPage)
def purchase_order_register(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    page: int = 1,
    page_size: int = 25,
    q: str | None = None,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    sort: str = "updated_desc",
    document_type: Literal["domestic_oils", "reagent"] = "domestic_oils",
    date_from: str | None = Query(None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"),
    date_to: str | None = Query(None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"),
) -> PurchaseOrderRegisterPage:
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="page must be positive and page_size must be between 1 and 100")
    statement = select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)).where(PurchaseOrder.document_type == document_type)
    for field, value in (("date_from", date_from), ("date_to", date_to)):
        if value is not None:
            try:
                bound = date.fromisoformat(value)
            except ValueError:
                raise HTTPException(status_code=422, detail=[{"loc": ["query", field], "msg": "Enter a valid date in YYYY-MM-DD format", "type": "value_error"}])
            statement = statement.where(PurchaseOrder.order_date >= bound if field == "date_from" else PurchaseOrder.order_date <= bound)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail=[{"loc": ["query", "date_to"], "msg": "End date must be on or after start date", "type": "value_error"}])
    if current_user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(current_user)
        statement = statement.where(PurchaseOrder.branch_id.in_(assigned) if assigned else false())
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where(or_(PurchaseOrder.purchase_order_number.ilike(pattern), PurchaseOrder.supplier_name.ilike(pattern), PurchaseOrder.purchaser_name.ilike(pattern)))
    if status_filter:
        statement = statement.where(PurchaseOrder.status == status_filter)
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    sort_column = PurchaseOrder.order_date if sort == "date_asc" else PurchaseOrder.updated_at if sort == "updated_desc" else PurchaseOrder.order_date
    statement = statement.order_by(sort_column.asc() if sort == "date_asc" else sort_column.desc(), PurchaseOrder.id.asc() if sort == "date_asc" else PurchaseOrder.id.desc()).offset((page - 1) * page_size).limit(page_size)
    return PurchaseOrderRegisterPage(items=list(db.scalars(statement)), total=total, page=page, page_size=page_size)


@router.get("/approval-queue", response_model=list[PurchaseOrderRead])
def purchase_order_approval_queue(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
) -> list[PurchaseOrder]:
    statement = select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)).where(PurchaseOrder.status == "pending_approval")
    if current_user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(current_user)
        statement = statement.where(PurchaseOrder.branch_id.in_(assigned) if assigned else false())
    return list(db.scalars(statement.order_by(PurchaseOrder.submitted_at.asc(), PurchaseOrder.id.asc())))


@router.get("/{purchase_order_id}", response_model=PurchaseOrderRead)
def get_purchase_order(
    purchase_order_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PurchaseOrder:
    return _get_purchase_order(db, current_user, purchase_order_id)


@router.delete("/{purchase_order_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def permanently_delete_purchase_order(
    purchase_order_id: int,
    request: BillDeleteRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> Response:
    delete_bill(db, current_user, "purchase_order", purchase_order_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _apply_purchase_order_update(db: Session, purchase_order: PurchaseOrder, request: PurchaseOrderUpdate) -> None:
    detail_fields = request.model_fields_set & {"reagent_details", "domestic_details"}
    if len(detail_fields) > 1:
        raise HTTPException(status_code=422, detail="Supply only one purchase-order details payload")
    details = None
    if detail_fields:
        detail_field = next(iter(detail_fields))
        details = getattr(request, detail_field)
        expected_type = "reagent" if detail_field == "reagent_details" else "domestic_oils"
        if details is None or details.document_type != expected_type or purchase_order.document_type != expected_type:
            raise HTTPException(status_code=422, detail="Details must match the saved purchase-order document type")
        if request.expected_version is None:
            raise HTTPException(status_code=422, detail="expected_version is required when editing purchase-order details")
        if details.branch_id not in (None, purchase_order.branch_id):
            raise HTTPException(status_code=422, detail="Seller profile cannot change during editing")

    number_changed = False
    number = request.purchase_order_number
    if details is not None and "purchase_order_number" in details.model_fields_set:
        nested_number = details.purchase_order_number
        if nested_number is None:
            raise HTTPException(status_code=422, detail={"field": "purchase_order_number", "message": "PO No. cannot be null"})
        if number is not None and number != nested_number:
            raise HTTPException(status_code=422, detail={"field": "purchase_order_number", "message": "Supply one consistent PO No."})
        number = nested_number
    if number is not None:
        if request.expected_version is None:
            raise HTTPException(status_code=422, detail="expected_version is required when editing a PO No.")
        number_changed = _set_purchase_order_number(db, purchase_order, number)
    if details is not None:
        branch = db.get(Branch, purchase_order.branch_id)
        supplier = _resolve_supplier(db, branch.id, details.supplier_id, details.supplier)
        if supplier.id != purchase_order.supplier_id:
            raise HTTPException(status_code=422, detail="Supplier cannot change during editing")
        supplier_state = details.supplier.address.state_code if details.supplier else supplier.state_code
        products, calculation = _calculate_purchase_order(db, branch, details, supplier_state, persist=True)
        _set_supplier_snapshot(purchase_order, supplier, details.supplier)
        if details.model_fields_set & {"purchaser_id", "purchaser"}:
            purchaser = _resolve_purchaser(db, branch.id, details.purchaser_id, details.purchaser, details.save_purchaser_for_future)
            purchase_order.purchaser_id = purchaser.id if purchaser else None
            _set_purchaser_snapshot(purchase_order, purchaser, details.purchaser)
        purchase_order.order_date = details.order_date
        purchase_order.expected_delivery_date = details.expected_delivery_date
        purchase_order.payment_terms = details.payment_terms
        if "transport_mode" in details.model_fields_set:
            purchase_order.transport_mode = details.transport_mode
        for field in ("freight_charges", "packing_charges", "other_charges", "discount_amount"):
            setattr(purchase_order, field, getattr(details, field))
        _set_reagent_details(purchase_order, details)
        _set_lines(purchase_order, products, calculation, [line.product_name for line in details.lines])
        for stored, submitted in zip(purchase_order.lines, details.lines, strict=True):
            stored.manufacturer_id = submitted.manufacturer_id if details.document_type == "reagent" else None
        _apply_calculation(purchase_order, calculation)
    for field, value in request.model_dump(exclude_unset=True, exclude={"expected_version", "reagent_details", "domestic_details", "purchase_order_number"}).items():
        setattr(purchase_order, field, value)
    if purchase_order.document_type == "reagent" or number_changed or details is not None:
        _clear_pdf_reference(purchase_order)


@router.patch("/{purchase_order_id}", response_model=PurchaseOrderRead)
def update_purchase_order(
    purchase_order_id: int,
    request: PurchaseOrderUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PurchaseOrder:
    purchase_order = _get_purchase_order(db, current_user, purchase_order_id, for_update=True)
    _require_version(purchase_order, request.expected_version)
    if purchase_order.status not in {"draft", "amendment_pending"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only draft or amendment-pending purchase orders can be edited")
    try:
        _apply_purchase_order_update(db, purchase_order, request)
        purchase_order.version += 1
        _record_revision(db, purchase_order, current_user, "draft_updated")
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(purchase_order)
    return purchase_order


@router.post("/{purchase_order_id}/submit", response_model=PurchaseOrderRead)
def submit_purchase_order(
    purchase_order_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: PurchaseOrderWorkflowAction | None = None,
) -> PurchaseOrder:
    purchase_order = _get_purchase_order(db, current_user, purchase_order_id, for_update=True)
    _require_version(purchase_order, request.expected_version if request else None)
    if purchase_order.status == "pending_approval":
        return purchase_order
    if purchase_order.status not in {"draft", "amendment_pending"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only draft or amendment-pending purchase orders can be submitted")
    _record_transition(db, purchase_order, current_user, "pending_approval", "Submitted for approval")
    db.commit()
    db.refresh(purchase_order)
    return purchase_order


@router.post("/{purchase_order_id}/approve", response_model=PurchaseOrderRead)
def approve_purchase_order(
    purchase_order_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
    request: PurchaseOrderWorkflowAction | None = None,
) -> PurchaseOrder:
    purchase_order = _get_purchase_order(db, current_user, purchase_order_id, for_update=True)
    _require_version(purchase_order, request.expected_version if request else None)
    if purchase_order.status != "pending_approval":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending purchase orders can be approved")
    if current_user.role != UserRole.ADMIN and (purchase_order.created_by_id == current_user.id or purchase_order.submitted_by_id == current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Independent approval is required; the creator or submitter cannot approve this purchase order")
    if purchase_order.submitted_revision != purchase_order.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The submitted revision is no longer current; submit the revised purchase order again")
    _record_transition(db, purchase_order, current_user, "approved", "Approved")
    db.commit()
    db.refresh(purchase_order)
    return purchase_order


@router.post("/{purchase_order_id}/amend", response_model=PurchaseOrderRead)
def amend_purchase_order(
    purchase_order_id: int,
    request: PurchaseOrderReasonAction,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PurchaseOrder:
    purchase_order = _get_purchase_order(db, current_user, purchase_order_id, for_update=True)
    _require_version(purchase_order, request.expected_version)
    if purchase_order.status != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved purchase orders can be amended")
    purchase_order.version += 1
    _record_transition(db, purchase_order, current_user, "amendment_pending", f"Amendment requested: {request.reason}")
    _record_revision(db, purchase_order, current_user, "amendment_requested", request.reason)
    if purchase_order.document_type == "reagent":
        _clear_pdf_reference(purchase_order)
    db.commit()
    db.refresh(purchase_order)
    return purchase_order


@router.post("/{purchase_order_id}/cancel", response_model=PurchaseOrderRead)
def cancel_purchase_order(
    purchase_order_id: int,
    request: PurchaseOrderReasonAction,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
) -> PurchaseOrder:
    purchase_order = _get_purchase_order(db, current_user, purchase_order_id, for_update=True)
    _require_version(purchase_order, request.expected_version)
    if purchase_order.status in {"cancelled", "closed"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Closed or cancelled purchase orders cannot be cancelled")
    purchase_order.cancellation_reason = request.reason
    _record_transition(db, purchase_order, current_user, "cancelled", f"Cancelled: {request.reason}")
    db.commit()
    db.refresh(purchase_order)
    return purchase_order


@router.post("/{purchase_order_id}/close", response_model=PurchaseOrderRead)
def close_purchase_order(
    purchase_order_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
    request: PurchaseOrderWorkflowAction | None = None,
) -> PurchaseOrder:
    purchase_order = _get_purchase_order(db, current_user, purchase_order_id, for_update=True)
    _require_version(purchase_order, request.expected_version if request else None)
    if purchase_order.status != "approved":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved purchase orders can be closed")
    _record_transition(db, purchase_order, current_user, "closed", "Closed")
    db.commit()
    db.refresh(purchase_order)
    return purchase_order


@router.post("/{purchase_order_id}/generate-pdf", response_model=PurchaseOrderRead)
def generate_purchase_order_pdf(
    purchase_order_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PurchaseOrder:
    purchase_order = _get_purchase_order(db, current_user, purchase_order_id, for_update=True)
    if purchase_order.document_type == "reagent" and purchase_order.status not in {"approved", "closed"}:
        raise HTTPException(status_code=409, detail="Approve the reagent purchase order before generating its final PDF")
    if purchase_order.pdf_storage_key and _pdf_file_path(purchase_order.pdf_storage_key).is_file():
        return purchase_order
    _generate_purchase_order_pdf(db, purchase_order, current_user)
    db.commit()
    db.refresh(purchase_order)
    return purchase_order


@router.get("/{purchase_order_id}/pdf")
def download_purchase_order_pdf(
    purchase_order_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> FileResponse:
    purchase_order = _get_purchase_order(db, current_user, purchase_order_id)
    if not purchase_order.pdf_storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order PDF not generated")
    pdf_path = _pdf_file_path(purchase_order.pdf_storage_key)
    if not pdf_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order PDF not found")
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"purchase-order-{purchase_order.id}.pdf",
    )
