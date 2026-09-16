from __future__ import annotations

import zlib
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import false, func, select, text
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, require_roles, resolve_branch_for_user
from app.db.session import get_db
from app.core.config import get_settings
from app.models.company import Branch, Company
from app.models.enums import InvoiceStatus, UserRole
from app.models.invoice import Invoice, InvoiceAuditLog, InvoiceLine, InvoiceNumberCounter
from app.models.master_records import BankAccount, Customer, Product, TermsAndConditions, Transporter
from app.models.user import User
from app.schemas.invoice import (
    InvoiceAuditLogRead,
    InvoiceCreate,
    InvoiceCustomerInput,
    InvoiceLineInput,
    InvoicePreviewLineRead,
    InvoicePreviewRead,
    InvoiceRead,
    InvoiceUpdate,
)
from app.services.invoice_calculator import InvoiceCalculationLine, calculate_invoice
from app.services.invoice_pdf import TEMPLATE_VERSION, build_invoice_context, render_invoice_pdf


router = APIRouter()


def financial_year_for(invoice_date) -> str:
    start_year = invoice_date.year if invoice_date.month >= 4 else invoice_date.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")


def _get_branch_for_access(db: Session, current_user: User, branch_id: int | None) -> Branch:
    return resolve_branch_for_user(db, current_user, branch_id)


def _get_customer_for_branch(db: Session, customer_id: int, branch_id: int, label: str) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None or customer.branch_id != branch_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{label} customer does not exist for this branch")
    return customer


def _validate_branch_record(db: Session, model, record_id: int | None, branch_id: int, label: str) -> None:
    if record_id is None:
        return
    record = db.get(model, record_id)
    if record is None or record.branch_id != branch_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"{label} does not exist for this branch")


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
    *,
    match_existing_gstin: bool = True,
) -> Customer:
    if match_existing_gstin and party.gstin:
        existing = db.scalar(
            select(Customer)
            .where(Customer.branch_id == branch_id, Customer.gstin == party.gstin, Customer.is_active.is_(True))
            .order_by(Customer.id)
        )
        if existing is not None:
            return existing
    existing_by_name = db.scalar(
        select(Customer)
        .where(
            Customer.branch_id == branch_id,
            func.lower(Customer.name) == party.name.strip().lower(),
            Customer.phone == party.phone,
            Customer.is_active.is_(True),
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
    if persist_inline:
        return _get_or_create_customer_from_inline(
            db,
            branch_id,
            inline_party,
            match_existing_gstin=label != "Consignee",
        )
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


def _manual_product_for_preview(branch_id: int, line: InvoiceLineInput) -> Product:
    product_name = _required_manual_line_value(line, "product_name").strip()
    return Product(
        branch_id=branch_id,
        name=product_name,
        description=line.description,
        hsn_sac=_required_manual_line_value(line, "hsn_sac").strip(),
        unit=_required_manual_line_value(line, "unit").strip(),
        base_rate=_required_manual_line_value(line, "rate"),
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
) -> tuple[Product, InvoiceCalculationLine]:
    if line.product_id is not None:
        product = db.get(Product, line.product_id)
        if product is None or product.branch_id != branch_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Product does not exist for this branch")
    else:
        product = _get_or_create_product_from_manual(db, branch_id, line) if persist_manual_products else _manual_product_for_preview(branch_id, line)
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


def _calculation_from_inputs(db: Session, branch: Branch, payload, *, persist_manual_products: bool) -> tuple[list[Product], object]:
    prepared = [_line_to_calculation(db, branch.id, line, persist_manual_products=persist_manual_products) for line in payload.lines]
    products = [product for product, _ in prepared]
    calculation_lines = [line for _, line in prepared]
    return products, calculate_invoice(
        branch_state_code=branch.state_code,
        place_of_supply_state_code=payload.place_of_supply_state_code,
        lines=calculation_lines,
        freight_charges=payload.freight_charges,
        packing_charges=payload.packing_charges,
        other_charges=payload.other_charges,
        discount_amount=payload.discount_amount,
    )


def _calculation_from_invoice(invoice: Invoice):
    return calculate_invoice(
        branch_state_code=invoice.branch_state_code,
        place_of_supply_state_code=invoice.place_of_supply_state_code,
        lines=[
            InvoiceCalculationLine(
                description=line.description,
                hsn_sac=line.hsn_sac,
                quantity=line.quantity,
                unit=line.unit,
                rate=line.rate,
                other_charge=line.other_charge,
                discount_amount=line.discount_amount,
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


def _set_consignee_snapshot(invoice: Invoice, consignee: Customer | None) -> None:
    if consignee is None:
        invoice.consignee_name = None
        invoice.consignee_gstin = None
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
    invoice.consignee_address_line1 = consignee.shipping_address_line1 if use_shipping else consignee.billing_address_line1
    invoice.consignee_address_line2 = consignee.shipping_address_line2 if use_shipping else consignee.billing_address_line2
    invoice.consignee_city = consignee.shipping_city if use_shipping else consignee.billing_city
    invoice.consignee_state = consignee.shipping_state if use_shipping else consignee.billing_state
    invoice.consignee_state_code = consignee.shipping_state_code if use_shipping else consignee.billing_state_code
    invoice.consignee_postal_code = consignee.shipping_postal_code if use_shipping else consignee.billing_postal_code


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


def _replace_lines(invoice: Invoice, products: list[Product], calculation) -> None:
    invoice.lines = [
        InvoiceLine(
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


def _apply_create_payload(db: Session, invoice: Invoice, current_user: User, payload: InvoiceCreate) -> None:
    branch = _get_branch_for_access(db, current_user, payload.branch_id)
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
    invoice.buyer_customer_id = buyer.id
    invoice.consignee_customer_id = consignee.id if consignee else None
    invoice.bank_account_id = bank_account.id if bank_account else None
    invoice.transporter_id = payload.transporter_id
    invoice.terms_and_conditions_id = payload.terms_and_conditions_id
    invoice.invoice_date = payload.invoice_date
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
    _set_buyer_snapshot(invoice, buyer)
    _set_consignee_snapshot(invoice, consignee)
    _set_bank_snapshot(invoice, bank_account, branch)
    _set_transporter_snapshot(invoice, transporter)
    _set_terms_snapshot(invoice, terms, branch)
    _replace_lines(invoice, products, calculation)
    _apply_calculation(invoice, calculation)


def _apply_update_payload(db: Session, invoice: Invoice, current_user: User, payload: InvoiceUpdate) -> None:
    if invoice.status != InvoiceStatus.DRAFT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approved or submitted invoices are immutable")

    branch = _get_branch_for_access(db, current_user, invoice.branch_id)
    updates = payload.model_dump(exclude_unset=True, exclude={"lines"})
    for field, value in updates.items():
        setattr(invoice, field, value)

    buyer = _get_customer_for_branch(db, invoice.buyer_customer_id, branch.id, "Buyer")
    consignee = _get_customer_for_branch(db, invoice.consignee_customer_id, branch.id, "Consignee") if invoice.consignee_customer_id else buyer
    bank_account = _get_bank_account_for_branch(db, invoice.bank_account_id, branch.id)
    transporter = db.get(Transporter, invoice.transporter_id) if invoice.transporter_id else None
    terms = db.get(TermsAndConditions, invoice.terms_and_conditions_id) if invoice.terms_and_conditions_id else None
    _validate_branch_record(db, Transporter, invoice.transporter_id, branch.id, "Transporter")
    _validate_branch_record(db, TermsAndConditions, invoice.terms_and_conditions_id, branch.id, "Terms and conditions")

    invoice.branch_name = branch.name
    invoice.branch_gstin = branch.gstin
    invoice.branch_state_code = branch.state_code
    _set_seller_snapshot(db, invoice, branch)
    _set_buyer_snapshot(invoice, buyer)
    _set_consignee_snapshot(invoice, consignee)
    _set_bank_snapshot(invoice, bank_account, branch)
    _set_transporter_snapshot(invoice, transporter)
    _set_terms_snapshot(invoice, terms, branch)

    if payload.lines is not None:
        input_payload = type(
            "PayloadForCalculation",
            (),
            {
                "lines": payload.lines,
                "place_of_supply_state_code": invoice.place_of_supply_state_code,
                "freight_charges": invoice.freight_charges,
                "packing_charges": invoice.packing_charges,
                "other_charges": invoice.other_charges,
                "discount_amount": invoice.discount_amount,
            },
        )
        products, calculation = _calculation_from_inputs(db, branch, input_payload, persist_manual_products=True)
        _replace_lines(invoice, products, calculation)
    else:
        calculation = _calculation_from_invoice(invoice)
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


def _record_transition(db: Session, invoice: Invoice, current_user: User, to_status: InvoiceStatus, note: str) -> None:
    if invoice.status == to_status:
        return
    from_status = invoice.status
    invoice.status = to_status
    now = datetime.now(UTC)
    if to_status == InvoiceStatus.PENDING_APPROVAL:
        invoice.submitted_by_id = current_user.id
        invoice.submitted_at = now
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


def _assign_invoice_number(db: Session, invoice: Invoice) -> None:
    if invoice.invoice_number is not None:
        return
    financial_year = financial_year_for(invoice.invoice_date)
    branch = db.get(Branch, invoice.branch_id)
    company_id = branch.company_id if branch is not None else invoice.branch_id
    # The visible PBPL sequence is company-wide because the requested format
    # has no branch/GSTIN component. The advisory lock makes this safe across
    # concurrent approvals, while the legacy counter table remains reusable
    # by anchoring the row to whichever company branch created it first.
    _lock_counter(db, invoice.branch_id, financial_year, company_id=company_id)
    counter = db.scalar(
        select(InvoiceNumberCounter)
        .join(Branch, Branch.id == InvoiceNumberCounter.branch_id)
        .where(
            Branch.company_id == company_id,
            InvoiceNumberCounter.financial_year == financial_year,
        )
        .with_for_update()
    )
    if counter is None:
        counter = InvoiceNumberCounter(branch_id=invoice.branch_id, financial_year=financial_year, next_sequence=1)
        db.add(counter)
        db.flush()
    highest_sequence = db.scalar(
        select(func.max(Invoice.invoice_sequence))
        .join(Branch, Branch.id == Invoice.branch_id)
        .where(
            Branch.company_id == company_id,
            Invoice.financial_year == financial_year,
        )
    ) or 0
    sequence = max(counter.next_sequence, highest_sequence + 1)
    counter.next_sequence = sequence + 1
    invoice.financial_year = financial_year
    invoice.invoice_sequence = sequence
    invoice.invoice_number = f"PBPL/{financial_year}/NO. {sequence:05d}"


@router.post("/preview", response_model=InvoicePreviewRead)
def preview_invoice(
    request: InvoiceCreate,
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
) -> Invoice:
    invoice = Invoice(created_by_id=current_user.id, amount_in_words="")
    _apply_create_payload(db, invoice, current_user, request)
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("", response_model=list[InvoiceRead])
def list_invoices(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    branch_id: int | None = None,
) -> list[Invoice]:
    statement = select(Invoice).options(selectinload(Invoice.lines)).order_by(Invoice.id)
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
        statement = statement.where(Invoice.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(current_user)
        statement = statement.where(Invoice.branch_id.in_(assigned) if assigned else false())
    return list(db.scalars(statement))


@router.get("/{invoice_id}", response_model=InvoiceRead)
def get_invoice(
    invoice_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Invoice:
    return _get_invoice(db, current_user, invoice_id)


@router.patch("/{invoice_id}", response_model=InvoiceRead)
def update_invoice(
    invoice_id: int,
    request: InvoiceUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Invoice:
    invoice = _get_invoice(db, current_user, invoice_id, for_update=True)
    _apply_update_payload(db, invoice, current_user, request)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/{invoice_id}/submit", response_model=InvoiceRead)
def submit_invoice(
    invoice_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Invoice:
    invoice = _get_invoice(db, current_user, invoice_id, for_update=True)
    if invoice.status == InvoiceStatus.PENDING_APPROVAL:
        return invoice
    if invoice.status != InvoiceStatus.DRAFT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only draft invoices can be submitted")
    _record_transition(db, invoice, current_user, InvoiceStatus.PENDING_APPROVAL, "Submitted for approval")
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/{invoice_id}/approve", response_model=InvoiceRead)
def approve_invoice(
    invoice_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.MANAGER))],
) -> Invoice:
    invoice = _get_invoice(db, current_user, invoice_id, for_update=True)
    if invoice.status in {InvoiceStatus.APPROVED, InvoiceStatus.PDF_GENERATED}:
        return invoice
    if invoice.status != InvoiceStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending invoices can be approved")
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
    _assign_invoice_number(db, invoice)
    _record_transition(db, invoice, current_user, InvoiceStatus.APPROVED, "Approved")
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
    result = render_invoice_pdf(context)
    storage_key = _write_pdf_bytes(invoice, result.pdf_bytes, result.sha256)
    invoice.pdf_sha256 = result.sha256
    invoice.pdf_template_version = TEMPLATE_VERSION
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
