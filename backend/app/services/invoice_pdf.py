from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, select_autoescape

if TYPE_CHECKING:
    from app.models.company import Branch, Company
    from app.models.invoice import Invoice
    from app.models.master_records import BankAccount, TermsAndConditions, Transporter
    from app.models.purchase_order import PurchaseOrder


TEMPLATE_VERSION = "a4-invoice-v11"
PURCHASE_ORDER_TEMPLATE_VERSION = "a4-purchase-order-v10"
REAGENT_BILL_TEMPLATE_VERSION = "a4-reagent-bill-v13"
REAGENT_PURCHASE_ORDER_TEMPLATE_VERSION = "a4-reagent-purchase-order-v13"
COPY_LABELS = (
    "Original for Recipient",
    "Duplicate for Transporter",
    "Triplicate for Supplier",
    "Extra",
)
_TEMPLATE_DIRECTORY = Path(__file__).resolve().parents[1] / "templates" / "invoice" / "v1"
_MONEY = Decimal("0.01")
_QUANTITY = Decimal("0.001")
_ZERO = Decimal("0.00")


def _load_default_logo_data_uri() -> str | None:
    # The supplied logo is retained as the source asset; this display copy removes
    # transparent canvas so contain-mode rendering never crops logo content.
    logo_path = _TEMPLATE_DIRECTORY / "pb-logo-trimmed.png"
    try:
        encoded_logo = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:image/png;base64,{encoded_logo}"


_DEFAULT_LOGO_DATA_URI = _load_default_logo_data_uri()


@dataclass(frozen=True)
class PdfSeller:
    legal_name: str
    trade_name: str | None
    logo_data_uri: str | None
    address_lines: tuple[str, ...]
    gstin: str
    contact: str | None
    pickup_address: str | None
    mark_text: str
    email_addresses: tuple[str, ...] = ()
    state_code: str | None = None
    state: str | None = None


@dataclass(frozen=True)
class PdfParty:
    heading: str
    name: str | None
    address_lines: tuple[str, ...]
    gstin: str | None
    contact: str | None
    pan: str | None = None
    shipment_lines: tuple[str, ...] = ()
    state_code: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class PdfLine:
    serial_number: int
    description: str
    hsn_sac: str
    quantity: Decimal
    unit: str
    base_rate: Decimal
    other_charge: Decimal
    discount: Decimal
    gst_rate: Decimal
    cess: Decimal
    amount: Decimal
    part_no: str | None = None
    discount_percent: Decimal = Decimal("0.00")
    product_name: str | None = None
    manufacturer_name: str | None = None
    manufacturer_code: str | None = None
    article_no: str | None = None
    pack_size: str | None = None
    cgst_rate: Decimal = Decimal("0.00")
    sgst_rate: Decimal = Decimal("0.00")
    igst_rate: Decimal = Decimal("0.00")
    cgst_amount: Decimal = Decimal("0.00")
    sgst_amount: Decimal = Decimal("0.00")
    igst_amount: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class InvoicePdfContext:
    seller: PdfSeller
    invoice_number: str | None
    invoice_date: date
    payment_terms: str | None
    po_number: str | None
    po_date: date | None
    irn: str | None
    signed_qr_data: str | None
    e_way_bill_number: str | None
    e_way_bill_date: date | None
    acknowledgement_number: str | None
    acknowledgement_date: date | None
    buyer: PdfParty
    consignee: PdfParty
    transport_mode: str | None
    vehicle_number: str | None
    vehicle_type: str | None
    lr_number: str | None
    lr_date: date | None
    expected_delivery_date: date | None
    lines: tuple[PdfLine, ...]
    total_quantity: Decimal
    amount_in_words: str
    bank_lines: tuple[str, ...]
    transporter_lines: tuple[str, ...]
    tax_rows: tuple[tuple[str, Decimal], ...]
    final_total: Decimal
    terms: tuple[str, ...]
    signed_by: str | None
    generated_at: datetime
    delivery_note_date: date | None = None
    copy_labels: tuple[str, ...] = COPY_LABELS
    powered_by: str | None = None
    document_title: str = "Tax Invoice"
    document_number_label: str = "Invoice No"
    document_date_label: str = "Invoice Date"
    document_footer_label: str = "Tax Invoice"
    template_version: str = TEMPLATE_VERSION
    show_discounts: bool = True
    bank_detail_rows: tuple[tuple[str, str], ...] = ()
    document_type: str = "sales"


@dataclass(frozen=True)
class PdfGenerationResult:
    pdf_bytes: bytes
    sha256: str


class PdfLayoutError(RuntimeError):
    """The full fixed bill and one indivisible product cannot fit on A4."""


def _clean_lines(*values: str | None) -> tuple[str, ...]:
    return tuple(value.strip() for value in values if value and value.strip())


def _join_contact(phone: str | None, email: str | None) -> str | None:
    values = _clean_lines(phone, email)
    return " | ".join(values) if values else None


def _seller_emails(document: Invoice | PurchaseOrder, legacy_primary: str | None) -> tuple[str, ...]:
    snapshot = getattr(document, "seller_email_addresses", None)
    # An empty list is intentional. Later profile edits never populate old bills.
    return _clean_lines(*snapshot) if snapshot is not None else _clean_lines(legacy_primary)


def _gst_summary_rows(document: Invoice | PurchaseOrder) -> list[tuple[str, Decimal]]:
    rates = sorted({line.gst_rate for line in document.lines if line.gst_rate > 0})

    def label(tax: str, divisor: Decimal) -> str:
        percentages = ", ".join(f"{format_percentage(rate / divisor)}%" for rate in rates)
        return f"{tax} @ {percentages}" if percentages else tax

    # Display the stored authoritative tax regime and totals; never recalculate
    # or split a saved IGST amount. Mixed rates are listed against the aggregate.
    if document.igst_amount:
        return [(label("IGST", Decimal("1")), document.igst_amount)]
    return [
        (label(tax, Decimal("2")), amount)
        for tax, amount in (("SGST", document.sgst_amount), ("CGST", document.cgst_amount))
        if amount
    ]


def _safe_image_data_uri(value: str | None) -> str | None:
    if value and re.fullmatch(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+", value):
        return value
    return None


def _initials(value: str) -> str:
    words = [word for word in re.split(r"\s+", value.strip()) if word]
    if not words:
        return ""
    return "".join(word[0] for word in words[:3]).upper()


def _date_or_none(value: date | None) -> date | None:
    return value


def _address_lines(
    address_line1: str | None,
    address_line2: str | None,
    city: str | None,
    state: str | None,
    postal_code: str | None,
) -> tuple[str, ...]:
    locality = ", ".join(part for part in (city, state) if part)
    if postal_code:
        locality = f"{locality} - {postal_code}" if locality else postal_code
    return _clean_lines(address_line1, address_line2, locality)


def _terms_lines(
    terms: TermsAndConditions | None,
    invoice: Invoice,
    branch: Branch | None = None,
) -> tuple[str, ...]:
    body = (
        invoice.terms_body
        if invoice.terms_body is not None
        else (terms.body if terms else (branch.terms_body if branch else None))
    )
    if not body:
        return ()
    return tuple(line.strip() for line in body.splitlines() if line.strip())


def build_invoice_context(
    invoice: Invoice,
    *,
    company: Company | None = None,
    branch: Branch | None = None,
    bank_account: BankAccount | None = None,
    transporter: Transporter | None = None,
    terms: TermsAndConditions | None = None,
    generated_at: datetime,
) -> InvoicePdfContext:
    is_sales_invoice = (invoice.document_type or "sales") == "sales"
    branch_address = _address_lines(
        invoice.seller_address_line1 or (branch.address_line1 if branch else None),
        invoice.seller_address_line2 or (branch.address_line2 if branch else None),
        invoice.seller_city or (branch.city if branch else None),
        invoice.seller_state or (branch.state if branch else None),
        invoice.seller_postal_code or (branch.postal_code if branch else None),
    )
    seller_name = invoice.seller_legal_name or (company.legal_name if company else invoice.branch_name)
    seller = PdfSeller(
        legal_name=seller_name,
        trade_name=invoice.seller_trade_name or (company.trade_name if company else None),
        logo_data_uri=_safe_image_data_uri(
            invoice.seller_logo_data_uri or (company.logo_data_uri if company else None)
        ),
        address_lines=(
            _clean_lines(*invoice.company_registered_address.splitlines())
            if getattr(invoice, "company_registered_address", None) is not None else branch_address
        ),
        gstin=invoice.branch_gstin,
        state_code=invoice.branch_state_code,
        state=invoice.seller_state or (branch.state if branch and branch.state_code == invoice.branch_state_code else None),
        contact=invoice.seller_phone or (branch.phone if branch else None),
        email_addresses=_seller_emails(invoice, invoice.seller_email or (branch.email if branch else None)),
        pickup_address=(
            invoice.pickup_address or None
            if getattr(invoice, "company_registered_address", None) is not None
            else (", ".join(branch_address) if branch_address else None)
        ),
        mark_text=_initials(seller_name),
    )

    buyer = PdfParty(
        heading="Buyer Details",
        name=invoice.buyer_name,
        address_lines=_address_lines(
            invoice.buyer_address_line1,
            invoice.buyer_address_line2,
            invoice.buyer_city,
            invoice.buyer_state,
            invoice.buyer_postal_code,
        ),
        gstin=invoice.buyer_gstin,
        contact=invoice.buyer_phone if is_sales_invoice else _join_contact(invoice.buyer_phone, invoice.buyer_email),
        email=invoice.buyer_email if is_sales_invoice else None,
        pan=invoice.buyer_pan,
    )
    consignee = PdfParty(
        heading="Consignee / Shipping Details",
        name=invoice.consignee_name,
        address_lines=_address_lines(
            invoice.consignee_address_line1,
            invoice.consignee_address_line2,
            invoice.consignee_city,
            invoice.consignee_state,
            invoice.consignee_postal_code,
        ),
        gstin=invoice.consignee_gstin,
        contact=invoice.consignee_phone if is_sales_invoice else _join_contact(invoice.consignee_phone, invoice.consignee_email),
        email=invoice.consignee_email if is_sales_invoice else None,
        pan=invoice.consignee_pan,
        shipment_lines=tuple(
            line
            for line in (
                f"Mode of Shipment: {invoice.transport_mode}" if invoice.transport_mode else None,
                f"Vehicle No: {invoice.vehicle_number}" if invoice.vehicle_number and invoice.document_type != "reagent" and not is_sales_invoice else None,
                f"Vehicle Type: {invoice.vehicle_type}" if invoice.vehicle_type else None,
                f"LR/Docket No.: {invoice.lr_number}" if invoice.lr_number and not is_sales_invoice else None,
                f"Trans Doc Date: {format_date(invoice.lr_date)}" if invoice.lr_date else None,
                f"Expected Delivery Date: {format_date(invoice.expected_delivery_date)}"
                if invoice.expected_delivery_date
                else None,
            )
            if line
        ),
    )

    bank_name = invoice.bank_name or (bank_account.bank_name if bank_account else (branch.bank_name if branch else None))
    bank_branch_name = invoice.bank_branch_name or (bank_account.branch_name if bank_account else (branch.bank_branch_name if branch else None))
    bank_account_name = invoice.bank_account_name or (bank_account.account_name if bank_account else (branch.bank_account_name if branch else None))
    bank_account_number = invoice.bank_account_number or (bank_account.account_number if bank_account else (branch.bank_account_number if branch else None))
    bank_ifsc_code = invoice.bank_ifsc_code or (bank_account.ifsc_code if bank_account else (branch.bank_ifsc_code if branch else None))
    bank_lines = tuple(
        line
        for line in (
            f"Bank Name: {bank_name}" if bank_name else None,
            f"Branch Name: {bank_branch_name}" if bank_branch_name else None,
            bank_account_name,
            f"A/C No.: {bank_account_number}" if bank_account_number else None,
            f"IFSC: {bank_ifsc_code}" if bank_ifsc_code else None,
        )
        if line
    )
    bank_detail_rows = tuple(
        (label, value)
        for label, value in (
            ("Our Bank.", bank_account_name or seller_name),
            ("Account No.", bank_account_number),
            ("IFSC Code.", bank_ifsc_code),
            ("PAN Card No.", invoice.seller_pan or (company.pan if company else None)),
        )
        if value
    )

    transporter_name = invoice.transporter_name or (transporter.name if transporter else None)
    transporter_gstin = invoice.transporter_gstin or (transporter.gstin if transporter else None)
    transporter_lines = tuple(
        line
        for line in (
            f"Transporter: {transporter_name}" if transporter_name else None,
            f"GSTIN: {transporter_gstin}" if transporter_gstin else None,
        )
        if line
    )

    tax_rows: list[tuple[str, Decimal]] = [("Taxable Value", invoice.taxable_value)]
    tax_rows.extend(_gst_summary_rows(invoice))
    tax_rows.extend(
        (
            ("Cess Amount", invoice.cess_amount),
            ("Discount Value", invoice.discount_amount),
            ("Round Off Amount", invoice.round_off),
        )
    )

    lines = tuple(
        PdfLine(
            serial_number=index,
            description=line.description,
            product_name=getattr(line, "product_name", None) or line.description,
            manufacturer_name=(
                getattr(line, "manufacturer_name", None)
                if invoice.document_type == "reagent"
                else None
            ),
            manufacturer_code=getattr(line, "manufacturer_code", None),
            article_no=getattr(line, "part_no", None) or getattr(line, "manufacturer_product_code", None),
            pack_size=getattr(line, "pack_size", None) if invoice.document_type == "reagent" else None,
            hsn_sac=line.hsn_sac,
            quantity=line.quantity,
            unit=line.unit,
            base_rate=line.rate,
            other_charge=line.other_charge,
            discount=line.discount_amount,
            gst_rate=line.gst_rate,
            cess=line.cess_amount,
            amount=line.taxable_value,
            part_no=line.part_no,
            discount_percent=line.discount_percent,
            cgst_rate=line.gst_rate / Decimal("2") if getattr(line, "cgst_amount", None) else _ZERO,
            sgst_rate=line.gst_rate / Decimal("2") if getattr(line, "sgst_amount", None) else _ZERO,
            igst_rate=line.gst_rate if getattr(line, "igst_amount", None) else _ZERO,
            cgst_amount=getattr(line, "cgst_amount", None) or _ZERO,
            sgst_amount=getattr(line, "sgst_amount", None) or _ZERO,
            igst_amount=getattr(line, "igst_amount", None) or _ZERO,
        )
        for index, line in enumerate(invoice.lines, start=1)
    )

    return InvoicePdfContext(
        seller=seller,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        delivery_note_date=_date_or_none(invoice.delivery_note_date),
        payment_terms=invoice.payment_terms,
        po_number=invoice.po_number,
        po_date=invoice.po_date,
        irn=invoice.irn,
        signed_qr_data=_safe_image_data_uri(invoice.signed_qr_data),
        e_way_bill_number=invoice.e_way_bill_number,
        e_way_bill_date=_date_or_none(invoice.e_way_bill_date),
        acknowledgement_number=invoice.acknowledgement_number,
        acknowledgement_date=_date_or_none(invoice.acknowledgement_date),
        buyer=buyer,
        consignee=consignee,
        transport_mode=invoice.transport_mode,
        vehicle_number=invoice.vehicle_number,
        vehicle_type=invoice.vehicle_type,
        lr_number=invoice.lr_number,
        lr_date=_date_or_none(invoice.lr_date),
        expected_delivery_date=_date_or_none(invoice.expected_delivery_date),
        lines=lines,
        total_quantity=sum((line.quantity for line in invoice.lines), Decimal("0.000")),
        amount_in_words=invoice.amount_in_words,
        bank_lines=bank_lines,
        transporter_lines=transporter_lines,
        tax_rows=tuple(tax_rows),
        final_total=invoice.final_total,
        terms=_terms_lines(terms, invoice, branch),
        signed_by=seller_name,
        generated_at=generated_at,
        bank_detail_rows=bank_detail_rows,
        document_type=invoice.document_type,
        template_version=REAGENT_BILL_TEMPLATE_VERSION if invoice.document_type == "reagent" else TEMPLATE_VERSION,
    )


def build_purchase_order_context(
    purchase_order: PurchaseOrder,
    *,
    company: Company | None = None,
    branch: Branch | None = None,
    bank_account: BankAccount | None = None,
    terms: TermsAndConditions | None = None,
    generated_at: datetime,
) -> InvoicePdfContext:
    branch_address = _address_lines(
        branch.address_line1 if branch else purchase_order.branch_name,
        branch.address_line2 if branch else None,
        branch.city if branch else None,
        branch.state if branch else None,
        branch.postal_code if branch else None,
    )
    seller_name = company.legal_name if company else purchase_order.branch_name
    seller = PdfSeller(
        legal_name=seller_name,
        trade_name=company.trade_name if company else None,
        logo_data_uri=_safe_image_data_uri(company.logo_data_uri if company else None),
        address_lines=(
            _clean_lines(*purchase_order.company_registered_address.splitlines())
            if getattr(purchase_order, "company_registered_address", None) is not None else branch_address
        ),
        gstin=purchase_order.branch_gstin,
        state_code=purchase_order.branch_state_code,
        state=branch.state if branch and branch.state_code == purchase_order.branch_state_code else None,
        contact=branch.phone if branch else None,
        email_addresses=_seller_emails(purchase_order, branch.email if branch else None),
        pickup_address=(
            purchase_order.pickup_address or None
            if getattr(purchase_order, "company_registered_address", None) is not None
            else (", ".join(branch_address) if branch_address else None)
        ),
        mark_text=_initials(seller_name),
    )
    supplier = PdfParty(
        heading="Seller",
        name=purchase_order.supplier_name,
        address_lines=_address_lines(
            purchase_order.supplier_address_line1,
            purchase_order.supplier_address_line2,
            purchase_order.supplier_city,
            purchase_order.supplier_state,
            purchase_order.supplier_postal_code,
        ),
        gstin=purchase_order.supplier_gstin,
        contact=purchase_order.supplier_phone,
        email=purchase_order.supplier_email,
        pan=purchase_order.supplier_pan,
        state_code=getattr(purchase_order, "supplier_state_code", None),
    )
    delivery = replace(
        supplier,
        heading="Seller / Shipping Address",
        shipment_lines=(
            (f"Expected Delivery Date: {format_date(purchase_order.expected_delivery_date)}",)
            if purchase_order.expected_delivery_date and getattr(purchase_order, "document_type", "domestic_oils") == "reagent"
            else ()
        ),
    )
    bank_name = bank_account.bank_name if bank_account else (branch.bank_name if branch else None)
    bank_branch_name = bank_account.branch_name if bank_account else (branch.bank_branch_name if branch else None)
    bank_account_name = bank_account.account_name if bank_account else (branch.bank_account_name if branch else None)
    bank_account_number = bank_account.account_number if bank_account else (branch.bank_account_number if branch else None)
    bank_ifsc_code = bank_account.ifsc_code if bank_account else (branch.bank_ifsc_code if branch else None)
    bank_lines = tuple(
        line
        for line in (
            f"Bank Name: {bank_name}" if bank_name else None,
            f"Branch Name: {bank_branch_name}" if bank_branch_name else None,
            bank_account_name,
            f"A/C No.: {bank_account_number}" if bank_account_number else None,
            f"IFSC: {bank_ifsc_code}" if bank_ifsc_code else None,
        )
        if line
    )
    bank_detail_rows = tuple(
        (label, value)
        for label, value in (
            ("Our Bank.", bank_account_name or seller_name),
            ("Account No.", bank_account_number),
            ("IFSC Code.", bank_ifsc_code),
            ("PAN Card No.", company.pan if company else None),
        )
        if value
    )
    terms_body = terms.body if terms else (branch.terms_body if branch else None)
    terms_lines = tuple(line.strip() for line in (terms_body or "").splitlines() if line.strip())
    tax_rows: list[tuple[str, Decimal]] = [("Taxable Value", purchase_order.taxable_value)]
    tax_rows.extend(_gst_summary_rows(purchase_order))
    tax_rows.extend(
        (
            ("Cess Amount", purchase_order.cess_amount),
            ("Round Off Amount", purchase_order.round_off),
        )
    )
    lines = tuple(
        PdfLine(
            serial_number=index,
            description=line.product_name,
            product_name=line.product_name,
            hsn_sac=line.hsn_sac,
            quantity=line.quantity,
            unit=line.unit,
            base_rate=line.rate,
            other_charge=line.other_charge,
            discount=line.discount_amount,
            gst_rate=line.gst_rate,
            cess=line.cess_amount,
            amount=line.taxable_value,
            cgst_rate=line.gst_rate / Decimal("2") if getattr(line, "cgst_amount", None) else _ZERO,
            sgst_rate=line.gst_rate / Decimal("2") if getattr(line, "sgst_amount", None) else _ZERO,
            igst_rate=line.gst_rate if getattr(line, "igst_amount", None) else _ZERO,
            cgst_amount=getattr(line, "cgst_amount", None) or _ZERO,
            sgst_amount=getattr(line, "sgst_amount", None) or _ZERO,
            igst_amount=getattr(line, "igst_amount", None) or _ZERO,
        )
        for index, line in enumerate(purchase_order.lines, start=1)
    )
    return InvoicePdfContext(
        seller=seller,
        invoice_number=purchase_order.purchase_order_number,
        invoice_date=purchase_order.order_date,
        delivery_note_date=None,
        payment_terms=purchase_order.payment_terms,
        po_number=None,
        po_date=None,
        irn=None,
        signed_qr_data=None,
        e_way_bill_number=None,
        e_way_bill_date=None,
        acknowledgement_number=None,
        acknowledgement_date=None,
        buyer=supplier,
        consignee=delivery,
        transport_mode=getattr(purchase_order, "transport_mode", None),
        vehicle_number=None,
        vehicle_type=None,
        lr_number=None,
        lr_date=None,
        expected_delivery_date=purchase_order.expected_delivery_date,
        lines=lines,
        total_quantity=sum((line.quantity for line in purchase_order.lines), Decimal("0.000")),
        amount_in_words=purchase_order.amount_in_words,
        bank_lines=bank_lines,
        transporter_lines=(),
        tax_rows=tuple(tax_rows),
        final_total=purchase_order.final_total,
        terms=terms_lines,
        signed_by=seller_name,
        generated_at=generated_at,
        copy_labels=("Purchase Order",),
        document_title="Purchase Order",
        document_number_label="PO No",
        document_date_label="PO Date",
        document_footer_label="Purchase Order",
        template_version=PURCHASE_ORDER_TEMPLATE_VERSION,
        show_discounts=False,
        bank_detail_rows=bank_detail_rows,
        document_type="purchase_order",
    )


def build_reagent_purchase_order_context(
    purchase_order: PurchaseOrder,
    *,
    company: Company | None = None,
    branch: Branch | None = None,
    bank_account: BankAccount | None = None,
    terms: TermsAndConditions | None = None,
    generated_at: datetime,
) -> InvoicePdfContext:
    """Reuse the reagent layout, without changing either existing document format."""
    context = build_purchase_order_context(purchase_order, company=company, branch=branch, bank_account=bank_account, terms=terms, generated_at=generated_at)
    buyer = context.buyer
    consignee = context.consignee
    consignee = replace(consignee, shipment_lines=_clean_lines(
        f"Mode of Shipment: {purchase_order.transport_mode}" if purchase_order.transport_mode else None,
        f"Vehicle Type: {purchase_order.vehicle_type}" if purchase_order.vehicle_type else None,
        f"LR No.: {purchase_order.lr_number}" if purchase_order.lr_number else None,
        f"LR Date: {format_date(purchase_order.lr_date)}" if purchase_order.lr_date else None,
        *consignee.shipment_lines,
    ))
    lines = tuple(replace(pdf_line,
        manufacturer_name=line.manufacturer_name, manufacturer_code=line.manufacturer_code,
        article_no=line.part_no or line.manufacturer_product_code, part_no=line.part_no,
        pack_size=getattr(line, "pack_size", None),
        discount_percent=line.discount_percent,
    ) for pdf_line, line in zip(context.lines, purchase_order.lines, strict=True))
    tax_rows = list(context.tax_rows)
    if purchase_order.discount_amount:
        tax_rows.insert(1, ("Discount Value", purchase_order.discount_amount))
    return replace(
        context, document_type="reagent", document_title="Purchase Order",
        document_footer_label="Reagent Purchase Order", template_version=REAGENT_PURCHASE_ORDER_TEMPLATE_VERSION,
        show_discounts=True, buyer=buyer, consignee=consignee,
        lines=lines, tax_rows=tuple(tax_rows), delivery_note_date=purchase_order.delivery_note_date,
        po_number=purchase_order.po_reference_number, po_date=purchase_order.po_reference_date,
        transport_mode=purchase_order.transport_mode, vehicle_number=purchase_order.vehicle_number,
        vehicle_type=purchase_order.vehicle_type, lr_number=purchase_order.lr_number, lr_date=purchase_order.lr_date,
    )


def _format_indian_integer(value: int) -> str:
    number = str(abs(value))
    if len(number) <= 3:
        return number
    last_three = number[-3:]
    prefix = number[:-3]
    groups: list[str] = []
    while prefix:
        groups.insert(0, prefix[-2:])
        prefix = prefix[:-2]
    return ",".join(groups + [last_three])


def format_money(value: Decimal) -> str:
    rounded = value.quantize(_MONEY, rounding=ROUND_HALF_UP)
    sign = "-" if rounded < 0 else ""
    absolute = abs(rounded)
    integer, fraction = f"{absolute:.2f}".split(".")
    return f"{sign}{_format_indian_integer(int(integer))}.{fraction}"


def format_quantity(value: Decimal) -> str:
    rounded = value.quantize(_QUANTITY, rounding=ROUND_HALF_UP)
    if rounded.is_zero():
        rounded = rounded.copy_abs()
    return format(rounded, ".3f").rstrip("0").rstrip(".")


def format_rate(value: Decimal) -> str:
    return f"{value.quantize(_MONEY, rounding=ROUND_HALF_UP):.2f}"


def format_percentage(value: Decimal) -> str:
    return format(value.normalize(), "f")


def format_date(value: date | None) -> str:
    return value.strftime("%d-%b-%Y") if value else ""


def build_invoice_html(context: InvoicePdfContext) -> str:
    return _build_paginated_html(context, _four_item_pages(context))


def _four_item_pages(context: InvoicePdfContext) -> tuple[tuple[PdfLine, ...], ...]:
    # Product rows (not their manufacturer/GST sublines) are the page boundary.
    return tuple(context.lines[start:start + 4] for start in range(0, len(context.lines), 4)) or ((),)


def _build_paginated_html(
    context: InvoicePdfContext, line_pages: tuple[tuple[PdfLine, ...], ...]
) -> str:
    environment = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIRECTORY),
        autoescape=select_autoescape(("html", "xml")),
    )
    template = environment.get_template("invoice.html")
    css = (_TEMPLATE_DIRECTORY / "invoice.css").read_text(encoding="utf-8")
    if context.template_version == REAGENT_PURCHASE_ORDER_TEMPLATE_VERSION:
        css += "\n" + (_TEMPLATE_DIRECTORY / "reagent_purchase_order.css").read_text(encoding="utf-8")
    return template.render(
        invoice=context,
        line_pages=line_pages,
        is_reagent_purchase_order=context.template_version == REAGENT_PURCHASE_ORDER_TEMPLATE_VERSION,
        template_version=context.template_version,
        css=css,
        format_money=format_money,
        format_quantity=format_quantity,
        format_rate=format_rate,
        format_percentage=format_percentage,
        format_date=format_date,
        default_logo_data_uri=_DEFAULT_LOGO_DATA_URI,
    )


def render_invoice_pdf(context: InvoicePdfContext) -> PdfGenerationResult:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as error:
        raise RuntimeError("Python Playwright is required to generate invoice PDFs") from error

    line_pages = _four_item_pages(context)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 734, "height": 1100})
            page.emulate_media(media="print")
            # A bounded split: long descriptions may need fewer than four rows,
            # but fixed bill sections must never spill onto a closing-only sheet.
            # Each split increases page count, which cannot exceed line count.
            for _ in range(max(1, len(context.lines))):
                page.set_content(_build_paginated_html(context, line_pages), wait_until="load")
                page.evaluate("() => document.fonts.ready")
                page.locator(".invoice-page").evaluate_all("""sheets => {
                    const bodies = sheets.map(s => s.querySelector('.items-table tbody'));
                    const words = sheets.map(s => s.querySelector('.amount-words'));
                    const wordHeight = Math.max(...words.map(n => n.getBoundingClientRect().height));
                    words.forEach(n => n.style.minHeight = `${wordHeight}px`);
                    const preferred = Math.max(...bodies.map(n => n.getBoundingClientRect().height));
                    bodies.forEach(n => n.style.height = 'auto');
                    let natural = Math.max(...bodies.map(n => n.getBoundingClientRect().height));
                    // Use the same table/settlement depth on every product page.
                    // Reclaim empty table space only when unusually tall fixed
                    // content needs it; never shrink or clip a product row.
                    const available = Math.min(...sheets.map((s, i) => {
                        const box = s.getBoundingClientRect();
                        const footer = s.querySelector('.invoice-footer').getBoundingClientRect();
                        const summary = s.querySelector('.summary-zone').getBoundingClientRect();
                        const closing = s.querySelector('.final-zone').getBoundingClientRect();
                        const unused = Math.max(0, closing.top - summary.bottom);
                        return bodies[i].getBoundingClientRect().height + unused + box.bottom - footer.bottom;
                    }));
                    if (natural > available) {
                        // Reagent layouts reserve 17 mm per product by default.
                        // Reclaim only that empty space before moving a product;
                        // align description/amount tax sublines at their real
                        // content height, without changing fonts or text.
                        sheets.forEach(s => s.querySelectorAll('.reagent-items-table tbody tr').forEach(row => {
                            const layouts = [...row.querySelectorAll('.item-description-layout, .item-amount-layout')];
                            layouts.forEach(n => n.style.minHeight = '0');
                            const required = Math.max(0, ...layouts.map(n => n.getBoundingClientRect().height));
                            layouts.forEach(n => n.style.minHeight = `${required}px`);
                        }));
                        natural = Math.max(...bodies.map(n => n.getBoundingClientRect().height));
                    }
                    const height = Math.max(natural, Math.min(preferred, available));
                    bodies.forEach(n => n.style.height = `${height}px`);
                }""")
                overflowing = page.locator(".invoice-page").evaluate_all("""sheets => sheets.flatMap((sheet, index) => {
                    const box = sheet.getBoundingClientRect();
                    const rect = selector => sheet.querySelector(selector)?.getBoundingClientRect();
                    const items = rect('.items-table');
                    const summary = rect('.summary-zone');
                    const terms = rect('.terms');
                    const signature = rect('.signature');
                    const footer = rect('.invoice-footer');
                    const closing = [terms, signature].filter(Boolean);
                    const spills = [...sheet.querySelectorAll('*')].some(node => {
                        const r = node.getBoundingClientRect();
                        return r.bottom > box.bottom + 1 || r.right > box.right + 1 || r.left < box.left - 1;
                    });
                    const overlaps = summary.top < items.bottom - 1 || closing.some(r =>
                        r.top < summary.bottom - 1 || r.bottom > footer.top + 1);
                    return spills || overlaps ? [index] : [];
                })""")
                if not overflowing:
                    break
                # Every copy has identical geometry; split each affected product
                # page once, not once per copy, preserving original serials/order.
                affected = {index % len(line_pages) for index in overflowing}
                # A tall multi-product body is shared with singleton pages for
                # equal settlement depth. Split that source before rejecting a
                # singleton inflated by it.
                splittable = {index for index in affected if len(line_pages[index]) > 1}
                if not splittable:
                    raise PdfLayoutError(
                        "Bill content cannot fit on A4 with its fixed sections. "
                        "Shorten the oversized description, address or terms and preview again."
                    )
                line_pages = tuple(
                    chunk
                    for index, lines in enumerate(line_pages)
                    for chunk in ((lines[:-1], lines[-1:]) if index in splittable else (lines,))
                )
            else:
                raise PdfLayoutError("Bill content cannot fit on A4 with its fixed sections")
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
        finally:
            browser.close()
    return PdfGenerationResult(pdf_bytes=pdf_bytes, sha256=hashlib.sha256(pdf_bytes).hexdigest())
