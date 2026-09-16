from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import false, func, select
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, resolve_branch_for_user
from app.api.v1.invoices import financial_year_for
from app.core.config import get_settings
from app.db.session import get_db
from app.models.company import Branch, Company
from app.models.enums import UserRole
from app.models.master_records import Product, Supplier
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.user import User
from app.schemas.invoice import InvoiceLineInput
from app.schemas.master_records import SupplierCreate
from app.schemas.purchase_order import PurchaseOrderCreate, PurchaseOrderRead
from app.services.invoice_calculator import InvoiceCalculationLine, calculate_invoice
from app.services.invoice_pdf import PURCHASE_ORDER_TEMPLATE_VERSION, build_purchase_order_context, render_invoice_pdf


router = APIRouter()

# Kept as a document-specific seam so tests and future purchase-order template
# changes do not need to know that Playwright is shared with invoice PDFs.
render_purchase_order_pdf = render_invoice_pdf


def _required_manual_line_value(line: InvoiceLineInput, field: str):
    value = getattr(line, field)
    if value is None or value == "":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Manual product line requires {field}",
        )
    return value


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


def _line_to_calculation(db: Session, branch_id: int, line: InvoiceLineInput) -> tuple[Product, InvoiceCalculationLine]:
    if line.product_id is not None:
        product = db.get(Product, line.product_id)
        if product is None or product.branch_id != branch_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Product does not exist for this branch")
    else:
        product = _get_or_create_product_from_manual(db, branch_id, line)
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
    if supplier_id is not None:
        supplier = db.get(Supplier, supplier_id)
        if supplier is None or supplier.branch_id != branch_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Supplier does not exist for this branch")
        return supplier
    if inline_supplier is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Supplier or supplier details are required",
        )
    return _supplier_from_inline(db, branch_id, inline_supplier)


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


def _set_lines(purchase_order: PurchaseOrder, products: list[Product], calculation) -> None:
    purchase_order.lines = [
        PurchaseOrderLine(
            product_id=product.id,
            sort_order=index + 1,
            product_name=product.name,
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


def _generate_purchase_order_pdf(db: Session, purchase_order: PurchaseOrder, current_user: User) -> PurchaseOrder:
    branch = db.get(Branch, purchase_order.branch_id)
    company = db.get(Company, branch.company_id) if branch else None
    generated_at = datetime.now(UTC)
    context = build_purchase_order_context(
        purchase_order,
        company=company,
        branch=branch,
        generated_at=generated_at,
    )
    result = render_purchase_order_pdf(context)
    storage_key = _write_pdf_bytes(purchase_order, result.pdf_bytes, result.sha256)
    purchase_order.pdf_sha256 = result.sha256
    purchase_order.pdf_template_version = PURCHASE_ORDER_TEMPLATE_VERSION
    purchase_order.pdf_storage_key = storage_key
    purchase_order.pdf_generated_by_id = current_user.id
    purchase_order.pdf_generated_at = generated_at
    return purchase_order


@router.post("", response_model=PurchaseOrderRead, status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    request: PurchaseOrderCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PurchaseOrder:
    branch = resolve_branch_for_user(db, current_user, request.branch_id)
    supplier = _resolve_supplier(db, branch.id, request.supplier_id, request.supplier)
    prepared = [_line_to_calculation(db, branch.id, line) for line in request.lines]
    products = [product for product, _ in prepared]
    calculation_lines = [line for _, line in prepared]
    calculation = calculate_invoice(
        branch_state_code=branch.state_code,
        place_of_supply_state_code=supplier.state_code,
        lines=calculation_lines,
        freight_charges=request.freight_charges,
        packing_charges=request.packing_charges,
        other_charges=request.other_charges,
        discount_amount=request.discount_amount,
    )
    purchase_order = PurchaseOrder(
        branch_id=branch.id,
        supplier_id=supplier.id,
        created_by_id=current_user.id,
        purchase_order_number=f"PO-DRAFT-{uuid4().hex}",
        order_date=request.order_date,
        expected_delivery_date=request.expected_delivery_date,
        payment_terms=request.payment_terms,
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
    db.add(purchase_order)
    db.flush()
    purchase_order.purchase_order_number = _create_purchase_order_number(branch, purchase_order.id, request.order_date)
    _set_lines(purchase_order, products, calculation)
    _apply_calculation(purchase_order, calculation)
    db.commit()
    db.refresh(purchase_order)
    return purchase_order


@router.get("", response_model=list[PurchaseOrderRead])
def list_purchase_orders(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    branch_id: int | None = None,
) -> list[PurchaseOrder]:
    statement = select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)).order_by(PurchaseOrder.id)
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
        statement = statement.where(PurchaseOrder.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(current_user)
        statement = statement.where(PurchaseOrder.branch_id.in_(assigned) if assigned else false())
    return list(db.scalars(statement))


@router.get("/{purchase_order_id}", response_model=PurchaseOrderRead)
def get_purchase_order(
    purchase_order_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PurchaseOrder:
    return _get_purchase_order(db, current_user, purchase_order_id)


@router.post("/{purchase_order_id}/generate-pdf", response_model=PurchaseOrderRead)
def generate_purchase_order_pdf(
    purchase_order_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PurchaseOrder:
    purchase_order = _get_purchase_order(db, current_user, purchase_order_id, for_update=True)
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
