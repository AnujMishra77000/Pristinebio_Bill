from __future__ import annotations

import zlib
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import false, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, require_roles, resolve_branch_for_user
from app.db.session import get_db
from app.core.config import get_settings
from app.models.company import Branch, Company
from app.models.enums import InvoiceStatus, UserRole
from app.models.invoice import Invoice, InvoiceAuditLog, InvoiceCreationRequest, InvoiceLine, InvoiceRevision
from app.models.master_records import BankAccount, Customer, Manufacturer, Product, Supplier, TermsAndConditions, Transporter
from app.models.user import User
from app.schemas.common import BillDeleteRequest
from app.schemas.invoice import (
    InvoiceAuditLogRead,
    InvoiceCreate,
    InvoiceCustomerInput,
    InvoiceLineInput,
    InvoicePreviewLineRead,
    InvoicePreviewRead,
    InvoicePreviewRequest,
    InvoiceRead,
    InvoiceUpdate,
    PdfPreviewRequest,
    RegisterPage,
    ReturnForCorrection,
    WorkflowAction,
)
from app.services.invoice_calculator import InvoiceCalculationLine, calculate_invoice
from app.services.invoice_pdf import PdfLayoutError, build_invoice_context, render_invoice_pdf
from app.services.financial_validation import FinancialValidationError
from app.services.idempotency import canonical_payload_hash, normalize_idempotency_key
from app.services.units import normalize_catalog_unit
from app.services.billing_addresses import company_address_snapshot, postal_address_lines
from app.services.customer_identity import find_customer_by_gstin, lock_customer_gstin, require_active_customer
from app.services.bill_deletion import delete_bill


router = APIRouter()


def financial_year_for(invoice_date) -> str:
    start_year = invoice_date.year if invoice_date.month >= 4 else invoice_date.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def invoice_number_prefix_for(invoice_date) -> str:
    return f"PBPL/{financial_year_for(invoice_date)}/"


def _set_manual_invoice_number(db: Session, invoice: Invoice, suffix: str) -> None:
    financial_year = financial_year_for(invoice.invoice_date)
    branch = db.get(Branch, invoice.branch_id)
    _lock_counter(db, invoice.branch_id, financial_year, company_id=branch.company_id)
    invoice_number = f"{invoice_number_prefix_for(invoice.invoice_date)}{suffix}"
    statement = select(Invoice.id).where(Invoice.invoice_number == invoice_number)
    if invoice.id is not None:
        statement = statement.where(Invoice.id != invoice.id)
    if db.scalar(statement) is not None:
        raise _invoice_number_conflict(invoice_number)
    invoice.invoice_number = invoice_number
    invoice.financial_year = financial_year
    invoice.invoice_sequence = None


def _invoice_number_conflict(invoice_number: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Invoice number {invoice_number} already exists",
    )


def _is_invoice_number_integrity_error(error: IntegrityError) -> bool:
    return "invoice_number" in str(error.orig).lower()


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")


def _get_branch_for_access(db: Session, current_user: User, branch_id: int | None) -> Branch:
    return resolve_branch_for_user(db, current_user, branch_id)


def _idempotency_key_or_422(value: str | None) -> str | None:
    try:
        return normalize_idempotency_key(value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


def _invoice_for_creation_request(db: Session, request: InvoiceCreationRequest) -> Invoice:
    if request.deleted_at is not None:
        raise HTTPException(status_code=410, detail={"code": "bill_deleted", "message": "This bill was permanently deleted. Start a new bill to reuse its number; the old save request cannot recreate it."})
    if request.invoice_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invoice creation is still being finalized; retry the same request")
    invoice = db.scalar(
        select(Invoice)
        .options(selectinload(Invoice.lines))
        .where(Invoice.id == request.invoice_id)
    )
    if invoice is None:
        # READ COMMITTED may observe DELETE after loading the creation request.
        # Query the scalar directly to avoid returning its stale identity-map row.
        if db.scalar(select(InvoiceCreationRequest.deleted_at).where(InvoiceCreationRequest.id == request.id)) is not None:
            raise HTTPException(status_code=410, detail={"code": "bill_deleted", "message": "This bill was permanently deleted. Start a new bill to reuse its number; the old save request cannot recreate it."})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Stored invoice idempotency record is invalid")
    return invoice


def _claim_invoice_creation(
    db: Session,
    branch_id: int,
    idempotency_key: str | None,
    payload_hash: str,
) -> tuple[InvoiceCreationRequest | None, Invoice | None]:
    if idempotency_key is None:
        return None, None
    creation_request = InvoiceCreationRequest(
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
            select(InvoiceCreationRequest).where(
                InvoiceCreationRequest.branch_id == branch_id,
                InvoiceCreationRequest.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key is being finalized; retry the same request") from None
        if existing.payload_hash != payload_hash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key was already used with a different payload")
        return None, _invoice_for_creation_request(db, existing)
    return creation_request, None


def _get_customer_for_branch(db: Session, customer_id: int, branch_id: int, label: str) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.branch_id != branch_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{label} customer does not exist for this branch")
    if not customer.is_active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{label} customer is inactive")
    return customer


def _validate_branch_record(db: Session, model, record_id: int | None, branch_id: int, label: str) -> None:
    if record_id is None:
        return
    record = db.get(model, record_id)
    if record is None or record.branch_id != branch_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{label} does not exist for this branch")
    if not getattr(record, "is_active", True):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{label} is inactive")


def _get_bank_account_for_branch(
    db: Session,
    bank_account_id: int | None,
    branch_id: int,
) -> BankAccount | None:
    statement = select(BankAccount).where(
        BankAccount.branch_id == branch_id,
        BankAccount.is_active.is_(True),
    )
    if bank_account_id is not None:
        bank_account = db.get(BankAccount, bank_account_id)
        if bank_account is None or bank_account.branch_id != branch_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Bank account does not exist for this branch",
            )
        if not bank_account.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Bank account is inactive",
            )
        return bank_account
    return db.scalar(statement.where(BankAccount.is_default.is_(True)).order_by(BankAccount.id))


def _set_seller_snapshot(db: Session, invoice: Invoice, branch: Branch) -> None:
    company = db.get(Company, branch.company_id)
    invoice.seller_legal_name = company.legal_name if company else branch.name
    invoice.seller_trade_name = company.trade_name if company else None
    invoice.seller_logo_data_uri = company.logo_data_uri if company else None
    invoice.seller_pan = company.pan if company else None
    invoice.seller_address_line1 = branch.address_line1
    invoice.seller_address_line2 = branch.address_line2
    invoice.seller_city = branch.city
    invoice.seller_state = branch.state
    invoice.seller_postal_code = branch.postal_code
    invoice.seller_phone = branch.phone
    invoice.seller_email = branch.email


def _pickup_supplier(db: Session, branch_id: int, supplier_id: int | None, *, use_default: bool = False) -> Supplier | None:
    if supplier_id is None and not use_default:
        return None
    statement = select(Supplier).where(Supplier.branch_id == branch_id)
    if supplier_id is not None:
        supplier = db.scalar(statement.where(Supplier.id == supplier_id))
        if supplier is None or not supplier.is_active:
            message = "Supplier is inactive; choose another active supplier" if supplier else "Supplier does not exist for this seller profile"
            raise HTTPException(status_code=422, detail={"field": "supplier_id", "message": message})
        return supplier
    return db.scalar(statement.where(Supplier.is_active.is_(True), Supplier.is_default.is_(True)).order_by(Supplier.id).limit(1))


def _set_pickup_snapshot(invoice: Invoice, supplier: Supplier | None) -> None:
    invoice.supplier_id = supplier.id if supplier else None
    invoice.pickup_address = ", ".join(postal_address_lines(supplier)) if supplier else ""


def _set_bank_snapshot(invoice: Invoice, bank_account: BankAccount | None, branch: Branch | None = None) -> None:
    invoice.bank_name = bank_account.bank_name if bank_account else (branch.bank_name if branch else None)
    invoice.bank_account_name = bank_account.account_name if bank_account else (branch.bank_account_name if branch else None)
    invoice.bank_account_number = bank_account.account_number if bank_account else (branch.bank_account_number if branch else None)
    invoice.bank_ifsc_code = bank_account.ifsc_code if bank_account else (branch.bank_ifsc_code if branch else None)
    invoice.bank_branch_name = bank_account.branch_name if bank_account else (branch.bank_branch_name if branch else None)


def _set_transporter_snapshot(invoice: Invoice, transporter: Transporter | None) -> None:
    invoice.transporter_name = transporter.name if transporter else None
    invoice.transporter_gstin = transporter.gstin if transporter else None


def _set_terms_snapshot(invoice: Invoice, terms: TermsAndConditions | None, branch: Branch | None = None) -> None:
    invoice.terms_title = terms.title if terms else None
    invoice.terms_body = terms.body if terms else (branch.terms_body if branch else None)


def _address_values(prefix: str, address: dict | None) -> dict[str, str | None]:
    if address is None:
        return {}
    return {f"{prefix}_{field}": value for field, value in address.items()}


def _get_or_create_customer_from_inline(
    db: Session,
    branch_id: int,
    party: InvoiceCustomerInput,
) -> Customer:
    if not party.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Inline customer details cannot be inactive for a new transaction",
        )
    if party.gstin:
        lock_customer_gstin(db, branch_id, party.gstin)
        existing = find_customer_by_gstin(db, branch_id, party.gstin)
        if existing is not None:
            return require_active_customer(existing)
    else:
        existing_by_name = db.scalar(
            select(Customer)
            .where(
                Customer.branch_id == branch_id,
                func.lower(Customer.name) == party.name.strip().lower(),
                Customer.phone == party.phone,
                Customer.is_active.is_(True),
                func.nullif(func.trim(Customer.gstin), "").is_(None),
            )
            .order_by(Customer.id)
        )
        if existing_by_name is not None:
            return existing_by_name

    values = party.model_dump(exclude={"billing_address", "shipping_address"})
    values["branch_id"] = branch_id
    values.update(_address_values("billing", party.billing_address.model_dump()))
    values.update(_address_values("shipping", party.shipping_address.model_dump() if party.shipping_address else None))
    customer = Customer(**values)
    db.add(customer)
    db.flush()
    return customer


def _resolve_customer(
    db: Session,
    branch_id: int,
    customer_id: int | None,
    inline_party: InvoiceCustomerInput | None,
    label: str,
    *,
    persist_inline: bool,
) -> Customer | None:
    if customer_id is not None:
        return _get_customer_for_branch(db, customer_id, branch_id, label)
    if inline_party is None:
        return None
    if not inline_party.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Inline {label.lower()} details cannot be inactive for a new transaction",
        )
    if persist_inline and label == "Buyer":
        return _get_or_create_customer_from_inline(db, branch_id, inline_party)
    # Manual consignee data belongs to this transaction, not the buyer master.
    address = inline_party.billing_address
    return Customer(
        branch_id=branch_id,
        name=inline_party.name,
        gstin=inline_party.gstin,
        pan=inline_party.pan,
        email=inline_party.email,
        phone=inline_party.phone,
        billing_name=address.name,
        billing_address_line1=address.address_line1,
        billing_address_line2=address.address_line2,
        billing_city=address.city,
        billing_state=address.state,
        billing_state_code=address.state_code,
        billing_postal_code=address.postal_code,
    )


def _required_manual_line_value(line: InvoiceLineInput, field: str):
    value = getattr(line, field)
    if value is None or value == "":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Manual product line requires {field}",
        )
    return value


def _get_or_create_product_from_manual(
    db: Session,
    branch_id: int,
    line: InvoiceLineInput,
    manufacturer: Manufacturer | None,
    *,
    generic_catalog: bool = False,
) -> Product:
    product_name = _required_manual_line_value(line, "product_name").strip()
    hsn_sac = _required_manual_line_value(line, "hsn_sac").strip()
    unit = _required_manual_line_value(line, "unit").strip()
    rate = _required_manual_line_value(line, "rate")
    gst_rate = _required_manual_line_value(line, "gst_rate")
    cess_rate = line.cess_rate if line.cess_rate is not None else Decimal("0.00")
    manufacturer_product_code = line.manufacturer_product_code or line.part_no

    if generic_catalog:
        existing = db.scalar(
            select(Product)
            .where(
                Product.branch_id == branch_id,
                Product.manufacturer_id.is_(None),
                func.lower(Product.name) == product_name.lower(),
                Product.hsn_sac == hsn_sac,
                Product.is_active.is_(True),
            )
            .order_by(Product.id)
        )
        if existing is not None:
            return existing

        product = Product(
            branch_id=branch_id,
            manufacturer_id=None,
            manufacturer_product_code=None,
            name=product_name,
            description=line.description,
            hsn_sac=hsn_sac,
            unit="kg",
            base_rate=Decimal("0.0000"),
            gst_rate=gst_rate,
            cess_rate=cess_rate,
            is_active=True,
        )
        db.add(product)
        db.flush()
        return product

    if manufacturer_product_code and manufacturer is not None:
        code_match = db.scalar(
            select(Product).where(
                Product.branch_id == branch_id,
                Product.manufacturer_id == manufacturer.id,
                Product.manufacturer_product_code == manufacturer_product_code,
            )
        )
        if code_match is not None:
            if code_match.name.casefold() != product_name.casefold():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This manufacturer product code is already assigned to a different product")
            if not code_match.is_active:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="The saved manufacturer product is inactive")
            return code_match

    existing = db.scalar(
        select(Product)
        .where(
            Product.branch_id == branch_id,
            Product.manufacturer_id == (manufacturer.id if manufacturer else None),
            Product.manufacturer_product_code == manufacturer_product_code,
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
        manufacturer_id=manufacturer.id if manufacturer else None,
        manufacturer_product_code=manufacturer_product_code,
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


def _manual_product_for_preview(
    branch_id: int,
    line: InvoiceLineInput,
    manufacturer: Manufacturer | None,
    *,
    generic_catalog: bool = False,
) -> Product:
    product_name = _required_manual_line_value(line, "product_name").strip()
    return Product(
        branch_id=branch_id,
        manufacturer_id=None if generic_catalog else (manufacturer.id if manufacturer else None),
        manufacturer_product_code=None if generic_catalog else (line.manufacturer_product_code or line.part_no),
        name=product_name,
        description=line.description,
        hsn_sac=_required_manual_line_value(line, "hsn_sac").strip(),
        unit="kg" if generic_catalog else _required_manual_line_value(line, "unit").strip(),
        base_rate=Decimal("0.0000") if generic_catalog else _required_manual_line_value(line, "rate"),
        gst_rate=_required_manual_line_value(line, "gst_rate"),
        cess_rate=line.cess_rate if line.cess_rate is not None else Decimal("0.00"),
        is_active=True,
    )


def _line_to_calculation(
    db: Session,
    branch_id: int,
    line: InvoiceLineInput,
    *,
    persist_manual_products: bool,
    require_manufacturer: bool,
) -> tuple[Product, InvoiceCalculationLine]:
    selected_manufacturer = None
    if line.manufacturer_id is not None:
        selected_manufacturer = db.get(Manufacturer, line.manufacturer_id)
        if selected_manufacturer is None or selected_manufacturer.branch_id != branch_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Manufacturer does not exist for this seller profile")
        if not selected_manufacturer.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Manufacturer is inactive")
    if require_manufacturer and selected_manufacturer is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Select an active manufacturer for each Reagent Bill line")

    if line.product_id is not None:
        product = db.get(Product, line.product_id)
        if product is None or product.branch_id != branch_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Product does not exist for this branch")
        if not product.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Product is inactive")
    else:
        product = (
            _get_or_create_product_from_manual(
                db,
                branch_id,
                line,
                selected_manufacturer,
                generic_catalog=require_manufacturer,
            )
            if persist_manual_products
            else _manual_product_for_preview(
                branch_id,
                line,
                selected_manufacturer,
                generic_catalog=require_manufacturer,
            )
        )

    manufacturer_id = product.manufacturer_id
    if (
        not require_manufacturer
        and line.product_id is not None
        and line.manufacturer_id is not None
        and line.manufacturer_id != manufacturer_id
    ):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Selected manufacturer does not match the saved product")
    manufacturer = selected_manufacturer if require_manufacturer else (db.get(Manufacturer, manufacturer_id) if manufacturer_id is not None else None)
    if manufacturer is not None:
        if manufacturer.branch_id != branch_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Manufacturer does not exist for this seller profile")
        if not manufacturer.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Manufacturer is inactive")
    unit = line.unit or product.unit
    if require_manufacturer:
        try:
            unit = normalize_catalog_unit(unit)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    manufacturer_product_code = (
        line.manufacturer_product_code or line.part_no
        if require_manufacturer
        else line.manufacturer_product_code or product.manufacturer_product_code or line.part_no
    )
    return (
        product,
        InvoiceCalculationLine(
            description=line.description or product.description or product.name,
            manufacturer_name=manufacturer.name if manufacturer else None,
            manufacturer_code=manufacturer.code if manufacturer else None,
            manufacturer_product_code=manufacturer_product_code,
            part_no=line.part_no or manufacturer_product_code,
            pack_size=line.pack_size if require_manufacturer else None,
            hsn_sac=line.hsn_sac or product.hsn_sac,
            quantity=line.quantity,
            unit=unit,
            rate=line.rate if line.rate is not None else product.base_rate,
            other_charge=line.other_charge,
            discount_amount=line.discount_amount,
            discount_percent=line.discount_percent,
            gst_rate=line.gst_rate if line.gst_rate is not None else product.gst_rate,
            cess_rate=line.cess_rate if line.cess_rate is not None else product.cess_rate,
        ),
    )


def _calculation_from_inputs(db: Session, branch: Branch, payload, *, persist_manual_products: bool) -> tuple[list[Product], object]:
    prepared = [
        _line_to_calculation(
            db,
            branch.id,
            line,
            persist_manual_products=persist_manual_products,
            require_manufacturer=payload.document_type == "reagent",
        )
        for line in payload.lines
    ]
    products = [product for product, _ in prepared]
    calculation_lines = [line for _, line in prepared]
    try:
        calculation = calculate_invoice(
            branch_state_code=branch.state_code,
            place_of_supply_state_code=payload.place_of_supply_state_code,
            lines=calculation_lines,
            freight_charges=payload.freight_charges,
            packing_charges=payload.packing_charges,
            other_charges=payload.other_charges,
            discount_amount=payload.discount_amount,
        )
    except FinancialValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return products, calculation


def _calculation_from_invoice(invoice: Invoice):
    return calculate_invoice(
        branch_state_code=invoice.branch_state_code,
        place_of_supply_state_code=invoice.place_of_supply_state_code,
        lines=[
            InvoiceCalculationLine(
                description=line.description,
                manufacturer_name=line.manufacturer_name,
                manufacturer_code=line.manufacturer_code,
                manufacturer_product_code=line.manufacturer_product_code,
                part_no=line.part_no,
                pack_size=line.pack_size,
                hsn_sac=line.hsn_sac,
                quantity=line.quantity,
                unit=line.unit,
                rate=line.rate,
                other_charge=line.other_charge,
                discount_amount=Decimal("0.00") if line.discount_percent else line.discount_amount,
                discount_percent=line.discount_percent,
                gst_rate=line.gst_rate,
                cess_rate=line.cess_rate,
            )
            for line in invoice.lines
        ],
        freight_charges=invoice.freight_charges,
        packing_charges=invoice.packing_charges,
        other_charges=invoice.other_charges,
        discount_amount=invoice.discount_amount,
    )


def _set_buyer_snapshot(invoice: Invoice, buyer: Customer) -> None:
    invoice.buyer_name = buyer.name
    invoice.buyer_gstin = buyer.gstin
    invoice.buyer_pan = buyer.pan
    invoice.buyer_email = buyer.email
    invoice.buyer_phone = buyer.phone
    invoice.buyer_address_line1 = buyer.billing_address_line1
    invoice.buyer_address_line2 = buyer.billing_address_line2
    invoice.buyer_city = buyer.billing_city
    invoice.buyer_state = buyer.billing_state
    invoice.buyer_state_code = buyer.billing_state_code
    invoice.buyer_postal_code = buyer.billing_postal_code


def _set_buyer_snapshot_from_input(invoice: Invoice, buyer: InvoiceCustomerInput) -> None:
    address = buyer.billing_address
    invoice.buyer_name = buyer.name
    invoice.buyer_gstin = buyer.gstin
    invoice.buyer_pan = buyer.pan
    invoice.buyer_email = buyer.email
    invoice.buyer_phone = buyer.phone
    invoice.buyer_address_line1 = address.address_line1
    invoice.buyer_address_line2 = address.address_line2
    invoice.buyer_city = address.city
    invoice.buyer_state = address.state
    invoice.buyer_state_code = address.state_code
    invoice.buyer_postal_code = address.postal_code


def _set_consignee_snapshot(invoice: Invoice, consignee: Customer | None) -> None:
    if consignee is None:
        invoice.consignee_name = None
        invoice.consignee_gstin = None
        invoice.consignee_pan = None
        invoice.consignee_email = None
        invoice.consignee_phone = None
        invoice.consignee_address_line1 = None
        invoice.consignee_address_line2 = None
        invoice.consignee_city = None
        invoice.consignee_state = None
        invoice.consignee_state_code = None
        invoice.consignee_postal_code = None
        return
    use_shipping = consignee.shipping_address_line1 is not None
    invoice.consignee_name = consignee.shipping_name if use_shipping else consignee.name
    invoice.consignee_gstin = consignee.gstin
    invoice.consignee_pan = consignee.pan
    invoice.consignee_email = consignee.email
    invoice.consignee_phone = consignee.phone
    invoice.consignee_address_line1 = consignee.shipping_address_line1 if use_shipping else consignee.billing_address_line1
    invoice.consignee_address_line2 = consignee.shipping_address_line2 if use_shipping else consignee.billing_address_line2
    invoice.consignee_city = consignee.shipping_city if use_shipping else consignee.billing_city
    invoice.consignee_state = consignee.shipping_state if use_shipping else consignee.billing_state
    invoice.consignee_state_code = consignee.shipping_state_code if use_shipping else consignee.billing_state_code
    invoice.consignee_postal_code = consignee.shipping_postal_code if use_shipping else consignee.billing_postal_code


def _set_consignee_snapshot_from_input(invoice: Invoice, consignee: InvoiceCustomerInput) -> None:
    address = consignee.shipping_address or consignee.billing_address
    invoice.consignee_name = address.name or consignee.name
    invoice.consignee_gstin = consignee.gstin
    invoice.consignee_pan = consignee.pan
    invoice.consignee_email = consignee.email
    invoice.consignee_phone = consignee.phone
    invoice.consignee_address_line1 = address.address_line1
    invoice.consignee_address_line2 = address.address_line2
    invoice.consignee_city = address.city
    invoice.consignee_state = address.state
    invoice.consignee_state_code = address.state_code
    invoice.consignee_postal_code = address.postal_code


def _apply_calculation(invoice: Invoice, calculation) -> None:
    invoice.taxable_value = calculation.taxable_value
    invoice.cgst_amount = calculation.cgst_amount
    invoice.sgst_amount = calculation.sgst_amount
    invoice.igst_amount = calculation.igst_amount
    invoice.cess_amount = calculation.cess_amount
    invoice.unrounded_total = calculation.unrounded_total
    invoice.round_off = calculation.round_off
    invoice.final_total = calculation.final_total
    invoice.amount_in_words = calculation.amount_in_words
    for stored_line, calculated_line in zip(invoice.lines, calculation.lines, strict=True):
        stored_line.taxable_value = calculated_line.taxable_value
        stored_line.cgst_amount = calculated_line.cgst_amount
        stored_line.sgst_amount = calculated_line.sgst_amount
        stored_line.igst_amount = calculated_line.igst_amount
        stored_line.cess_amount = calculated_line.cess_amount
        stored_line.other_charge = calculated_line.other_charge
        stored_line.line_total = calculated_line.line_total
        stored_line.part_no = calculated_line.part_no
        stored_line.pack_size = calculated_line.pack_size
        stored_line.manufacturer_name = calculated_line.manufacturer_name
        stored_line.manufacturer_code = calculated_line.manufacturer_code
        stored_line.manufacturer_product_code = calculated_line.manufacturer_product_code
        stored_line.discount_amount = calculated_line.discount_amount
        stored_line.discount_percent = calculated_line.discount_percent


def _replace_lines(invoice: Invoice, products: list[Product], calculation, product_names: list[str | None] | None = None) -> None:
    invoice.lines = [
        InvoiceLine(
            product_id=product.id,
            sort_order=index + 1,
            product_name=(product_names[index] or product.name) if product_names is not None else product.name,
            description=line.description,
            manufacturer_name=line.manufacturer_name,
            manufacturer_code=line.manufacturer_code,
            manufacturer_product_code=line.manufacturer_product_code,
            part_no=line.part_no,
            pack_size=line.pack_size,
            hsn_sac=line.hsn_sac,
            quantity=line.quantity,
            unit=line.unit,
            rate=line.rate,
            other_charge=line.other_charge,
            discount_amount=line.discount_amount,
            discount_percent=line.discount_percent,
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


def _apply_create_payload(db: Session, invoice: Invoice, current_user: User, payload: InvoiceCreate) -> None:
    branch = _get_branch_for_access(db, current_user, payload.branch_id)
    pickup_supplier = _pickup_supplier(db, branch.id, payload.supplier_id, use_default="supplier_id" not in payload.model_fields_set)
    buyer = _resolve_customer(db, branch.id, payload.buyer_customer_id, payload.buyer, "Buyer", persist_inline=True)
    if buyer is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Buyer customer or buyer details are required",
        )
    consignee = _resolve_customer(
        db,
        branch.id,
        payload.consignee_customer_id,
        payload.consignee,
        "Consignee",
        persist_inline=True,
    ) or buyer
    bank_account = _get_bank_account_for_branch(db, payload.bank_account_id, branch.id)
    transporter = db.get(Transporter, payload.transporter_id) if payload.transporter_id else None
    terms = db.get(TermsAndConditions, payload.terms_and_conditions_id) if payload.terms_and_conditions_id else None
    _validate_branch_record(db, Transporter, payload.transporter_id, branch.id, "Transporter")
    _validate_branch_record(db, TermsAndConditions, payload.terms_and_conditions_id, branch.id, "Terms and conditions")
    products, calculation = _calculation_from_inputs(db, branch, payload, persist_manual_products=True)

    invoice.branch_id = branch.id
    invoice.document_type = payload.document_type
    invoice.buyer_customer_id = buyer.id
    invoice.consignee_customer_id = consignee.id if consignee else None
    invoice.bank_account_id = bank_account.id if bank_account else None
    invoice.transporter_id = payload.transporter_id
    invoice.terms_and_conditions_id = payload.terms_and_conditions_id
    invoice.invoice_date = payload.invoice_date
    _set_manual_invoice_number(db, invoice, payload.invoice_number_suffix)
    invoice.delivery_note_date = payload.delivery_note_date
    invoice.place_of_supply_state_code = payload.place_of_supply_state_code
    invoice.po_number = payload.po_number
    invoice.po_date = payload.po_date
    invoice.payment_terms = payload.payment_terms
    invoice.due_date = payload.due_date
    invoice.irn = payload.irn
    invoice.signed_qr_data = payload.signed_qr_data
    invoice.e_way_bill_number = payload.e_way_bill_number
    invoice.e_way_bill_date = payload.e_way_bill_date
    invoice.acknowledgement_number = payload.acknowledgement_number
    invoice.acknowledgement_date = payload.acknowledgement_date
    invoice.transport_mode = payload.transport_mode
    invoice.vehicle_number = payload.vehicle_number
    invoice.vehicle_type = payload.vehicle_type
    invoice.lr_number = payload.lr_number
    invoice.lr_date = payload.lr_date
    invoice.expected_delivery_date = payload.expected_delivery_date
    invoice.freight_charges = payload.freight_charges
    invoice.packing_charges = payload.packing_charges
    invoice.other_charges = payload.other_charges
    invoice.discount_amount = payload.discount_amount
    invoice.branch_name = branch.name
    invoice.branch_gstin = branch.gstin
    invoice.branch_state_code = branch.state_code
    _set_seller_snapshot(db, invoice, branch)
    invoice.company_registered_address = company_address_snapshot(db.get(Company, branch.company_id), branch)
    invoice.seller_email_addresses = [email for email in (branch.email, branch.secondary_email) if email]
    # Empty is an intentional absent pickup, not a fallback to the company address.
    _set_pickup_snapshot(invoice, pickup_supplier)
    if payload.buyer is not None:
        _set_buyer_snapshot_from_input(invoice, payload.buyer)
    else:
        _set_buyer_snapshot(invoice, buyer)
    if payload.consignee is not None:
        _set_consignee_snapshot_from_input(invoice, payload.consignee)
    elif payload.consignee_customer_id is not None:
        _set_consignee_snapshot(invoice, consignee)
    elif payload.buyer is not None:
        _set_consignee_snapshot_from_input(invoice, payload.buyer)
    else:
        _set_consignee_snapshot(invoice, buyer)
    _set_bank_snapshot(invoice, bank_account, branch)
    _set_transporter_snapshot(invoice, transporter)
    _set_terms_snapshot(invoice, terms, branch)
    _replace_lines(invoice, products, calculation)
    _apply_calculation(invoice, calculation)


def _apply_update_payload(db: Session, invoice: Invoice, current_user: User, payload: InvoiceUpdate) -> None:
    if invoice.status != InvoiceStatus.DRAFT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approved or submitted invoices are immutable")

    branch = _get_branch_for_access(db, current_user, invoice.branch_id)
    fields_set = payload.model_fields_set
    if payload.branch_id is not None and payload.branch_id != invoice.branch_id:
        raise HTTPException(status_code=422, detail="Seller profile cannot change during editing")
    if fields_set & {"buyer", "consignee", "supplier_id"} and payload.expected_version is None:
        raise HTTPException(status_code=422, detail="expected_version is required when editing inline parties or pickup supplier")
    if "supplier_id" in fields_set and (
        payload.supplier_id != invoice.supplier_id
        or (payload.supplier_id is None and bool(invoice.pickup_address))
    ):
        supplier = _pickup_supplier(db, branch.id, payload.supplier_id)
        if invoice.company_registered_address is None:
            # Explicit editing of an old draft opts into distinct pickup data,
            # retaining its old header instead of refreshing it from a master.
            invoice.company_registered_address = "\n".join(postal_address_lines(invoice, prefix="seller_")) or "\n".join(postal_address_lines(branch))
        _set_pickup_snapshot(invoice, supplier)
    for label, party in (("Buyer", payload.buyer), ("Consignee", payload.consignee)):
        if party is not None and party.branch_id not in (None, branch.id):
            raise HTTPException(status_code=422, detail=f"{label} seller profile does not match")
        if party is not None and not party.is_active:
            raise HTTPException(status_code=422, detail=f"Inline {label.lower()} details cannot be inactive for a new transaction")
    previous_invoice_date = invoice.invoice_date
    updates_with_lines = payload.model_dump(exclude_unset=True)
    if "lines" in fields_set and payload.lines is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Invoice lines cannot be null")
    for field in (
        "invoice_date",
        "place_of_supply_state_code",
        "freight_charges",
        "packing_charges",
        "other_charges",
        "discount_amount",
    ):
        if field in updates_with_lines and updates_with_lines[field] is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{field.replace('_', ' ').title()} cannot be null")

    updates = payload.model_dump(
        exclude_unset=True,
        exclude={"lines", "expected_version", "invoice_number_suffix", "branch_id", "buyer", "consignee", "buyer_customer_id", "consignee_customer_id", "supplier_id"},
    )
    for field, value in updates.items():
        setattr(invoice, field, value)

    if "invoice_number_suffix" in fields_set:
        _set_manual_invoice_number(db, invoice, payload.invoice_number_suffix)
    elif "invoice_date" in fields_set and invoice.invoice_number is not None:
        previous_prefix = invoice_number_prefix_for(previous_invoice_date)
        if previous_prefix != invoice_number_prefix_for(invoice.invoice_date):
            if not invoice.invoice_number.startswith(previous_prefix):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Enter the invoice number when changing the financial year")
            _set_manual_invoice_number(db, invoice, invoice.invoice_number[len(previous_prefix):])

    if fields_set & {"buyer_customer_id", "buyer"}:
        buyer = _resolve_customer(db, branch.id, payload.buyer_customer_id, payload.buyer, "Buyer", persist_inline=True)
        if buyer is None:
            raise HTTPException(status_code=422, detail="Buyer customer or buyer details are required")
        invoice.buyer_customer_id = buyer.id
        if payload.buyer is not None:
            _set_buyer_snapshot_from_input(invoice, payload.buyer)
        else:
            _set_buyer_snapshot(invoice, buyer)

    if fields_set & {"consignee_customer_id", "consignee"}:
        consignee = _resolve_customer(db, branch.id, payload.consignee_customer_id, payload.consignee, "Consignee", persist_inline=True)
        if payload.consignee is not None:
            invoice.consignee_customer_id = consignee.id
            _set_consignee_snapshot_from_input(invoice, payload.consignee)
        elif consignee is not None:
            invoice.consignee_customer_id = consignee.id
            _set_consignee_snapshot(invoice, consignee)
        else:
            invoice.consignee_customer_id = invoice.buyer_customer_id
            # Copy the edited transaction, never rehydrate it from a customer master.
            for field in ("name", "gstin", "pan", "email", "phone", "address_line1", "address_line2", "city", "state", "state_code", "postal_code"):
                setattr(invoice, f"consignee_{field}", getattr(invoice, f"buyer_{field}"))

    if "bank_account_id" in fields_set:
        if invoice.bank_account_id is None:
            _set_bank_snapshot(invoice, None)
        else:
            bank_account = _get_bank_account_for_branch(db, invoice.bank_account_id, branch.id)
            _set_bank_snapshot(invoice, bank_account)

    if "transporter_id" in fields_set:
        if invoice.transporter_id is None:
            _set_transporter_snapshot(invoice, None)
        else:
            _validate_branch_record(db, Transporter, invoice.transporter_id, branch.id, "Transporter")
            _set_transporter_snapshot(invoice, db.get(Transporter, invoice.transporter_id))

    if "terms_and_conditions_id" in fields_set:
        if invoice.terms_and_conditions_id is None:
            _set_terms_snapshot(invoice, None)
        else:
            _validate_branch_record(db, TermsAndConditions, invoice.terms_and_conditions_id, branch.id, "Terms and conditions")
            _set_terms_snapshot(invoice, db.get(TermsAndConditions, invoice.terms_and_conditions_id))

    if payload.lines is not None:
        input_payload = type(
            "PayloadForCalculation",
            (),
            {
                "document_type": invoice.document_type,
                "lines": payload.lines,
                "place_of_supply_state_code": invoice.place_of_supply_state_code,
                "freight_charges": invoice.freight_charges,
                "packing_charges": invoice.packing_charges,
                "other_charges": invoice.other_charges,
                "discount_amount": invoice.discount_amount,
            },
        )
        products, calculation = _calculation_from_inputs(db, branch, input_payload, persist_manual_products=True)
        _replace_lines(invoice, products, calculation, [line.product_name for line in payload.lines])
    else:
        try:
            calculation = _calculation_from_invoice(invoice)
        except FinancialValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    _apply_calculation(invoice, calculation)


def _get_invoice(db: Session, current_user: User, invoice_id: int, *, for_update: bool = False) -> Invoice:
    statement = select(Invoice).options(selectinload(Invoice.lines)).where(Invoice.id == invoice_id)
    if for_update:
        statement = statement.with_for_update()
    invoice = db.scalar(statement)
    if invoice is None:
        raise _not_found()
    ensure_branch_access(current_user, invoice.branch_id)
    return invoice


def _version_conflict(invoice: Invoice) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "version_conflict",
            "message": "This invoice was changed by another user. Reload it before saving.",
            "current_version": invoice.version,
        },
    )


def _require_version(invoice: Invoice, expected_version: int | None) -> None:
    # Existing API clients may omit this during their transition. Current entry
    # screens send the value and therefore receive optimistic concurrency safety.
    if expected_version is not None and expected_version != invoice.version:
        raise _version_conflict(invoice)


def _revision_snapshot(invoice: Invoice) -> dict:
    return {
        "seller_addresses": {"company_registered_address": invoice.company_registered_address, "pickup_address": invoice.pickup_address, "supplier_id": invoice.supplier_id, "email_addresses": invoice.seller_email_addresses},
        "document_type": invoice.document_type,
        "invoice_date": invoice.invoice_date.isoformat(),
        "buyer": {field: getattr(invoice, f"buyer_{field}") for field in ("name", "gstin", "pan", "email", "phone", "address_line1", "address_line2", "city", "state", "state_code", "postal_code")},
        "consignee": {field: getattr(invoice, f"consignee_{field}") for field in ("name", "gstin", "pan", "email", "phone", "address_line1", "address_line2", "city", "state", "state_code", "postal_code")},
        "totals": {"taxable_value": str(invoice.taxable_value), "cgst_amount": str(invoice.cgst_amount), "sgst_amount": str(invoice.sgst_amount), "igst_amount": str(invoice.igst_amount), "cess_amount": str(invoice.cess_amount), "final_total": str(invoice.final_total)},
        "lines": [{"sort_order": line.sort_order, "product_name": line.product_name, "description": line.description, "manufacturer_name": line.manufacturer_name, "manufacturer_code": line.manufacturer_code, "manufacturer_product_code": line.manufacturer_product_code, "part_no": line.part_no, "pack_size": line.pack_size, "hsn_sac": line.hsn_sac, "quantity": str(line.quantity), "unit": line.unit, "rate": str(line.rate), "discount_percent": str(line.discount_percent), "discount_amount": str(line.discount_amount), "line_total": str(line.line_total)} for line in invoice.lines],
    }


def _record_revision(db: Session, invoice: Invoice, current_user: User, event: str, reason: str | None = None) -> None:
    db.add(InvoiceRevision(invoice_id=invoice.id, revision=invoice.version, event=event, actor_user_id=current_user.id, reason=reason, snapshot=_revision_snapshot(invoice)))


def _record_transition(db: Session, invoice: Invoice, current_user: User, to_status: InvoiceStatus, note: str) -> None:
    if invoice.status == to_status:
        return
    from_status = invoice.status
    invoice.status = to_status
    now = datetime.now(UTC)
    if to_status == InvoiceStatus.PENDING_APPROVAL:
        invoice.submitted_by_id = current_user.id
        invoice.submitted_at = now
        invoice.submitted_revision = invoice.version
    elif to_status == InvoiceStatus.APPROVED:
        invoice.approved_by_id = current_user.id
        invoice.approved_at = now
    elif to_status == InvoiceStatus.PDF_GENERATED:
        invoice.pdf_generated_by_id = current_user.id
        invoice.pdf_generated_at = now
    db.add(
        InvoiceAuditLog(
            invoice_id=invoice.id,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=current_user.id,
            note=note,
        )
    )


def _lock_counter(db: Session, branch_id: int, financial_year: str, *, company_id: int | None = None) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        scope_id = company_id if company_id is not None else branch_id
        key = zlib.crc32(f"invoice-number:{scope_id}:{financial_year}".encode())
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


@router.post("/preview", response_model=InvoicePreviewRead)
def preview_invoice(
    request: InvoicePreviewRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> InvoicePreviewRead:
    branch = _get_branch_for_access(db, current_user, request.branch_id)
    buyer = _resolve_customer(db, branch.id, request.buyer_customer_id, request.buyer, "Buyer", persist_inline=False)
    if buyer is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Buyer customer or buyer details are required",
        )
    if request.consignee_customer_id or request.consignee:
        _resolve_customer(db, branch.id, request.consignee_customer_id, request.consignee, "Consignee", persist_inline=False)
    _get_bank_account_for_branch(db, request.bank_account_id, branch.id)
    _pickup_supplier(db, branch.id, request.supplier_id, use_default="supplier_id" not in request.model_fields_set)
    _validate_branch_record(db, Transporter, request.transporter_id, branch.id, "Transporter")
    _validate_branch_record(db, TermsAndConditions, request.terms_and_conditions_id, branch.id, "Terms and conditions")
    _, calculation = _calculation_from_inputs(db, branch, request, persist_manual_products=False)
    return InvoicePreviewRead(
        lines=[InvoicePreviewLineRead(**asdict(line)) for line in calculation.lines],
        taxable_value=calculation.taxable_value,
        cgst_amount=calculation.cgst_amount,
        sgst_amount=calculation.sgst_amount,
        igst_amount=calculation.igst_amount,
        cess_amount=calculation.cess_amount,
        unrounded_total=calculation.unrounded_total,
        round_off=calculation.round_off,
        final_total=calculation.final_total,
        amount_in_words=calculation.amount_in_words,
    )


@router.post("", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
def create_invoice(
    request: InvoiceCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Invoice:
    branch = _get_branch_for_access(db, current_user, request.branch_id)
    normalized_key = _idempotency_key_or_422(idempotency_key)
    # Omitted/blank pack sizes must preserve hashes of pre-field save requests.
    hash_exclusions = {"lines": {index: {"pack_size"} for index, line in enumerate(request.lines) if line.pack_size is None}}
    if "supplier_id" not in request.model_fields_set:
        hash_exclusions["supplier_id"] = True
    payload_hash = canonical_payload_hash(request, exclude=hash_exclusions)
    if normalized_key is not None:
        existing_request = db.scalar(
            select(InvoiceCreationRequest).where(
                InvoiceCreationRequest.branch_id == branch.id,
                InvoiceCreationRequest.idempotency_key == normalized_key,
            )
        )
        if existing_request is not None:
            if existing_request.payload_hash != payload_hash:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key was already used with a different payload")
            response.status_code = status.HTTP_200_OK
            return _invoice_for_creation_request(db, existing_request)

    try:
        creation_request, replay = _claim_invoice_creation(db, branch.id, normalized_key, payload_hash)
        if replay is not None:
            response.status_code = status.HTTP_200_OK
            return replay
        invoice = Invoice(created_by_id=current_user.id, amount_in_words="")
        _apply_create_payload(db, invoice, current_user, request)
        db.add(invoice)
        db.flush()
        _record_revision(db, invoice, current_user, "created")
        if creation_request is not None:
            creation_request.invoice_id = invoice.id
        db.commit()
        db.refresh(invoice)
        return invoice
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as error:
        db.rollback()
        if _is_invoice_number_integrity_error(error) and invoice.invoice_number:
            raise _invoice_number_conflict(invoice.invoice_number) from None
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A conflicting billing record was created concurrently. Retry using the same save request.",
        ) from None
    except Exception:
        db.rollback()
        raise


@router.get("", response_model=list[InvoiceRead])
def list_invoices(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    branch_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    document_type: Literal["sales", "reagent"] = Query("sales"),
) -> list[Invoice]:
    statement = select(Invoice).options(selectinload(Invoice.lines)).where(Invoice.document_type == document_type).order_by(Invoice.id)
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
        statement = statement.where(Invoice.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(current_user)
        statement = statement.where(Invoice.branch_id.in_(assigned) if assigned else false())
    return list(db.scalars(statement.limit(limit)))


@router.get("/register", response_model=RegisterPage)
def invoice_register(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    page: int = 1,
    page_size: int = 25,
    q: str | None = None,
    status_filter: Annotated[InvoiceStatus | None, Query(alias="status")] = None,
    sort: str = "updated_desc",
    document_type: Literal["sales", "reagent"] = Query("sales"),
    date_from: str | None = Query(None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"),
    date_to: str | None = Query(None, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"),
) -> RegisterPage:
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="page must be positive and page_size must be between 1 and 100")
    statement = select(Invoice).options(selectinload(Invoice.lines)).where(Invoice.document_type == document_type)
    for field, value in (("date_from", date_from), ("date_to", date_to)):
        if value is not None:
            try:
                bound = date.fromisoformat(value)
            except ValueError:
                raise HTTPException(status_code=422, detail=[{"loc": ["query", field], "msg": "Enter a valid date in YYYY-MM-DD format", "type": "value_error"}])
            statement = statement.where(Invoice.invoice_date >= bound if field == "date_from" else Invoice.invoice_date <= bound)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail=[{"loc": ["query", "date_to"], "msg": "End date must be on or after start date", "type": "value_error"}])
    if current_user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(current_user)
        statement = statement.where(Invoice.branch_id.in_(assigned) if assigned else false())
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where(or_(Invoice.invoice_number.ilike(pattern), Invoice.buyer_name.ilike(pattern), Invoice.po_number.ilike(pattern)))
    if status_filter is not None:
        statement = statement.where(Invoice.status == status_filter)
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    sort_column = Invoice.invoice_date if sort == "date_asc" else Invoice.updated_at if sort == "updated_desc" else Invoice.invoice_date
    statement = statement.order_by(sort_column.asc() if sort == "date_asc" else sort_column.desc(), Invoice.id.asc() if sort == "date_asc" else Invoice.id.desc()).offset((page - 1) * page_size).limit(page_size)
    return RegisterPage(items=list(db.scalars(statement)), total=total, page=page, page_size=page_size)


@router.get("/approval-queue", response_model=list[InvoiceRead])
def invoice_approval_queue(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
) -> list[Invoice]:
    statement = select(Invoice).options(selectinload(Invoice.lines)).where(Invoice.status == InvoiceStatus.PENDING_APPROVAL)
    if current_user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(current_user)
        statement = statement.where(Invoice.branch_id.in_(assigned) if assigned else false())
    return list(db.scalars(statement.order_by(Invoice.submitted_at.asc(), Invoice.id.asc())))


@router.get("/{invoice_id}", response_model=InvoiceRead)
def get_invoice(
    invoice_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Invoice:
    return _get_invoice(db, current_user, invoice_id)


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def permanently_delete_invoice(
    invoice_id: int,
    request: BillDeleteRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> Response:
    delete_bill(db, current_user, "invoice", invoice_id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{invoice_id}", response_model=InvoiceRead)
def update_invoice(
    invoice_id: int,
    request: InvoiceUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Invoice:
    invoice = _get_invoice(db, current_user, invoice_id, for_update=True)
    _require_version(invoice, request.expected_version)
    invoice_number = (
        f"{invoice_number_prefix_for(request.invoice_date or invoice.invoice_date)}{request.invoice_number_suffix}"
        if request.invoice_number_suffix is not None else invoice.invoice_number
    )
    try:
        _apply_update_payload(db, invoice, current_user, request)
        invoice.version += 1
        _record_revision(db, invoice, current_user, "draft_updated")
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as error:
        db.rollback()
        if _is_invoice_number_integrity_error(error) and invoice_number:
            raise _invoice_number_conflict(invoice_number) from None
        raise
    db.refresh(invoice)
    return invoice


@router.post("/{invoice_id}/submit", response_model=InvoiceRead)
def submit_invoice(
    invoice_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    request: WorkflowAction | None = None,
) -> Invoice:
    invoice = _get_invoice(db, current_user, invoice_id, for_update=True)
    _require_version(invoice, request.expected_version if request else None)
    if invoice.status == InvoiceStatus.PENDING_APPROVAL:
        return invoice
    if invoice.status != InvoiceStatus.DRAFT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only draft invoices can be submitted")
    if not invoice.invoice_number:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Enter an invoice number on the draft before submitting it")
    _record_transition(db, invoice, current_user, InvoiceStatus.PENDING_APPROVAL, "Submitted for approval")
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/{invoice_id}/approve", response_model=InvoiceRead)
def approve_invoice(
    invoice_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
    request: WorkflowAction | None = None,
) -> Invoice:
    invoice = _get_invoice(db, current_user, invoice_id, for_update=True)
    _require_version(invoice, request.expected_version if request else None)
    if invoice.status in {InvoiceStatus.APPROVED, InvoiceStatus.PDF_GENERATED}:
        return invoice
    if invoice.status != InvoiceStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending invoices can be approved")
    if current_user.role != UserRole.ADMIN and (invoice.submitted_by_id == current_user.id or invoice.created_by_id == current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Independent approval is required; the creator or submitter cannot approve this invoice")
    if invoice.submitted_revision != invoice.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The submitted revision is no longer current; submit the revised invoice again")
    if not invoice.invoice_number:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Return this invoice for correction and enter an invoice number before approval")
    branch = db.get(Branch, invoice.branch_id)
    bank_account = _get_bank_account_for_branch(db, invoice.bank_account_id, invoice.branch_id)
    transporter = db.get(Transporter, invoice.transporter_id) if invoice.transporter_id else None
    terms = db.get(TermsAndConditions, invoice.terms_and_conditions_id) if invoice.terms_and_conditions_id else None
    if branch is not None:
        _set_seller_snapshot(db, invoice, branch)
    _set_bank_snapshot(invoice, bank_account, branch)
    _set_transporter_snapshot(invoice, transporter)
    _set_terms_snapshot(invoice, terms, branch)
    calculation = _calculation_from_invoice(invoice)
    _apply_calculation(invoice, calculation)
    _record_transition(db, invoice, current_user, InvoiceStatus.APPROVED, "Approved")
    invoice.approved_revision = invoice.version
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/{invoice_id}/return-for-correction", response_model=InvoiceRead)
def return_invoice_for_correction(
    invoice_id: int,
    request: ReturnForCorrection,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
) -> Invoice:
    invoice = _get_invoice(db, current_user, invoice_id, for_update=True)
    _require_version(invoice, request.expected_version)
    if invoice.status != InvoiceStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending invoices can be returned for correction")
    invoice.returned_reason = request.reason
    invoice.version += 1
    _record_transition(db, invoice, current_user, InvoiceStatus.DRAFT, f"Returned for correction: {request.reason}")
    _record_revision(db, invoice, current_user, "returned_for_correction", request.reason)
    db.commit()
    db.refresh(invoice)
    return invoice


def _pdf_storage_directory() -> Path:
    configured = Path(get_settings().pdf_storage_dir)
    return configured if configured.is_absolute() else Path.cwd() / configured


def _pdf_file_path(storage_key: str) -> Path:
    directory = _pdf_storage_directory().resolve()
    path = (directory / storage_key).resolve()
    if path.parent != directory:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid stored PDF path")
    return path


def _write_pdf_bytes(invoice: Invoice, pdf_bytes: bytes, sha256: str) -> str:
    import uuid

    directory = _pdf_storage_directory()
    directory.mkdir(parents=True, exist_ok=True)
    storage_key = f"invoice-{invoice.id}-{sha256[:16]}.pdf"
    final_path = directory / storage_key
    temporary_path = directory / f".{storage_key}.{uuid.uuid4().hex}.tmp"
    temporary_path.write_bytes(pdf_bytes)
    temporary_path.replace(final_path)
    return storage_key


def _invoice_pdf_context(db: Session, invoice: Invoice, generated_at: datetime):
    branch = db.get(Branch, invoice.branch_id)
    company = db.get(Company, branch.company_id) if branch else None
    bank_account = db.get(BankAccount, invoice.bank_account_id) if invoice.bank_account_id else None
    transporter = db.get(Transporter, invoice.transporter_id) if invoice.transporter_id else None
    terms = db.get(TermsAndConditions, invoice.terms_and_conditions_id) if invoice.terms_and_conditions_id else None
    return build_invoice_context(
        invoice,
        company=company,
        branch=branch,
        bank_account=bank_account,
        transporter=transporter,
        terms=terms,
        generated_at=generated_at,
    )


@router.post("/{invoice_id}/preview-pdf", response_class=Response)
def preview_invoice_pdf(
    invoice_id: int,
    request: PdfPreviewRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Response:
    # Hold the same row lock as draft edits while taking this exact revision's
    # rendering snapshot. No calculation, master refresh or billing write occurs.
    invoice = _get_invoice(db, current_user, invoice_id, for_update=True)
    _require_version(invoice, request.expected_version)
    context = _invoice_pdf_context(db, invoice, datetime.now(UTC))
    try:
        result = render_invoice_pdf(context)
    except PdfLayoutError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return Response(
        content=result.pdf_bytes,
        media_type="application/pdf",
        headers={"Cache-Control": "no-store", "Content-Disposition": f'inline; filename="invoice-{invoice.id}-preview.pdf"'},
    )


def _generate_invoice_pdf(db: Session, invoice: Invoice, current_user: User) -> Invoice:
    branch = db.get(Branch, invoice.branch_id)
    company = db.get(Company, branch.company_id) if branch else None
    bank_account = db.get(BankAccount, invoice.bank_account_id) if invoice.bank_account_id else None
    transporter = db.get(Transporter, invoice.transporter_id) if invoice.transporter_id else None
    terms = db.get(TermsAndConditions, invoice.terms_and_conditions_id) if invoice.terms_and_conditions_id else None
    generated_at = datetime.now(UTC)
    context = build_invoice_context(
        invoice,
        company=company,
        branch=branch,
        bank_account=bank_account,
        transporter=transporter,
        terms=terms,
        generated_at=generated_at,
    )
    try:
        result = render_invoice_pdf(context)
    except PdfLayoutError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    storage_key = _write_pdf_bytes(invoice, result.pdf_bytes, result.sha256)
    invoice.pdf_sha256 = result.sha256
    invoice.pdf_template_version = context.template_version
    invoice.pdf_storage_key = storage_key
    _record_transition(db, invoice, current_user, InvoiceStatus.PDF_GENERATED, "PDF generated")
    return invoice


@router.post("/{invoice_id}/generate-pdf", response_model=InvoiceRead)
@router.post("/{invoice_id}/mark-pdf-generated", response_model=InvoiceRead)
def generate_invoice_pdf(
    invoice_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
) -> Invoice:
    invoice = _get_invoice(db, current_user, invoice_id, for_update=True)
    if invoice.status == InvoiceStatus.PDF_GENERATED:
        if invoice.pdf_storage_key and _pdf_file_path(invoice.pdf_storage_key).is_file():
            return invoice
    if invoice.status != InvoiceStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved invoices can generate a PDF")
    _generate_invoice_pdf(db, invoice, current_user)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> FileResponse:
    invoice = _get_invoice(db, current_user, invoice_id)
    if not invoice.pdf_storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice PDF not generated")
    pdf_path = _pdf_file_path(invoice.pdf_storage_key)
    if not pdf_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice PDF not found")
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=f"invoice-{invoice.id}.pdf",
    )


@router.get("/{invoice_id}/audit", response_model=list[InvoiceAuditLogRead])
def list_invoice_audit(
    invoice_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[InvoiceAuditLog]:
    invoice = _get_invoice(db, current_user, invoice_id)
    return list(
        db.scalars(
            select(InvoiceAuditLog)
            .where(InvoiceAuditLog.invoice_id == invoice.id)
            .order_by(InvoiceAuditLog.id)
        )
    )
