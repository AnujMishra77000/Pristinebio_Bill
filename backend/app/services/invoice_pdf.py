from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
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


TEMPLATE_VERSION = "a4-invoice-v1"
PURCHASE_ORDER_TEMPLATE_VERSION = "a4-purchase-order-v1"
COPY_LABELS = (
    "Original for Recipient",
    "Duplicate for Transporter",
    "Triplicate for Supplier",
    "Extra",
)
_TEMPLATE_DIRECTORY = Path(__file__).resolve().parents[1] / "templates" / "invoice" / "v1"
_MONEY = Decimal("0.01")
_QUANTITY = Decimal("0.001")


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


@dataclass(frozen=True)
class PdfParty:
    heading: str
    name: str | None
    address_lines: tuple[str, ...]
    gstin: str | None
    contact: str | None
    shipment_lines: tuple[str, ...] = ()


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


@dataclass(frozen=True)
class PdfGenerationResult:
    pdf_bytes: bytes
    sha256: str


def _clean_lines(*values: str | None) -> tuple[str, ...]:
    return tuple(value.strip() for value in values if value and value.strip())


def _join_contact(phone: str | None, email: str | None) -> str | None:
    values = _clean_lines(phone, email)
    return " | ".join(values) if values else None


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
        address_lines=branch_address,
        gstin=invoice.branch_gstin,
        contact=_join_contact(
            invoice.seller_phone or (branch.phone if branch else None),
            invoice.seller_email or (branch.email if branch else None),
        ),
        pickup_address=", ".join(branch_address) if branch_address else None,
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
        contact=_join_contact(invoice.buyer_phone, invoice.buyer_email),
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
        contact=None,
        shipment_lines=tuple(
            line
            for line in (
                f"Mode of Shipment: {invoice.transport_mode}" if invoice.transport_mode else None,
                f"Vehicle No: {invoice.vehicle_number}" if invoice.vehicle_number else None,
                f"Vehicle Type: {invoice.vehicle_type}" if invoice.vehicle_type else None,
                f"LR/Docket No.: {invoice.lr_number}" if invoice.lr_number else None,
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
    if invoice.igst_amount:
        tax_rows.append(("IGST", invoice.igst_amount))
    else:
        if invoice.sgst_amount:
            tax_rows.append(("SGST", invoice.sgst_amount))
        if invoice.cgst_amount:
            tax_rows.append(("CGST", invoice.cgst_amount))
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
            hsn_sac=line.hsn_sac,
            quantity=line.quantity,
            unit=line.unit,
            base_rate=line.rate,
            other_charge=line.other_charge,
            discount=line.discount_amount,
            gst_rate=line.gst_rate,
            cess=line.cess_amount,
            amount=line.line_total,
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
    )


def build_purchase_order_context(
    purchase_order: PurchaseOrder,
    *,
    company: Company | None = None,
    branch: Branch | None = None,
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
        address_lines=branch_address,
        gstin=purchase_order.branch_gstin,
        contact=_join_contact(
            branch.phone if branch else None,
            branch.email if branch else None,
        ),
        pickup_address=", ".join(branch_address) if branch_address else None,
        mark_text=_initials(seller_name),
    )
    supplier = PdfParty(
        heading="Supplier Details",
        name=purchase_order.supplier_name,
        address_lines=_address_lines(
            purchase_order.supplier_address_line1,
            purchase_order.supplier_address_line2,
            purchase_order.supplier_city,
            purchase_order.supplier_state,
            purchase_order.supplier_postal_code,
        ),
        gstin=purchase_order.supplier_gstin,
        contact=_join_contact(purchase_order.supplier_phone, purchase_order.supplier_email),
    )
    delivery = PdfParty(
        heading="Delivery Details",
        name=purchase_order.branch_name,
        address_lines=branch_address,
        gstin=purchase_order.branch_gstin,
        contact=None,
        shipment_lines=(
            (f"Expected Delivery Date: {format_date(purchase_order.expected_delivery_date)}",)
            if purchase_order.expected_delivery_date
            else ()
        ),
    )
    tax_rows: list[tuple[str, Decimal]] = [("Taxable Value", purchase_order.taxable_value)]
    if purchase_order.igst_amount:
        tax_rows.append(("IGST", purchase_order.igst_amount))
    else:
        if purchase_order.sgst_amount:
            tax_rows.append(("SGST", purchase_order.sgst_amount))
        if purchase_order.cgst_amount:
            tax_rows.append(("CGST", purchase_order.cgst_amount))
    tax_rows.extend(
        (
            ("Cess Amount", purchase_order.cess_amount),
            ("Discount Value", purchase_order.discount_amount),
            ("Round Off Amount", purchase_order.round_off),
        )
    )
    lines = tuple(
        PdfLine(
            serial_number=index,
            description=line.description or line.product_name,
            hsn_sac=line.hsn_sac,
            quantity=line.quantity,
            unit=line.unit,
            base_rate=line.rate,
            other_charge=line.other_charge,
            discount=line.discount_amount,
            gst_rate=line.gst_rate,
            cess=line.cess_amount,
            amount=line.line_total,
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
        transport_mode=None,
        vehicle_number=None,
        vehicle_type=None,
        lr_number=None,
        lr_date=None,
        expected_delivery_date=purchase_order.expected_delivery_date,
        lines=lines,
        total_quantity=sum((line.quantity for line in purchase_order.lines), Decimal("0.000")),
        amount_in_words=purchase_order.amount_in_words,
        bank_lines=(),
        transporter_lines=(),
        tax_rows=tuple(tax_rows),
        final_total=purchase_order.final_total,
        terms=(),
        signed_by=seller_name,
        generated_at=generated_at,
        copy_labels=("Purchase Order",),
        document_title="Purchase Order",
        document_number_label="PO No",
        document_date_label="PO Date",
        document_footer_label="Purchase Order",
        template_version=PURCHASE_ORDER_TEMPLATE_VERSION,
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
    return f"{rounded:.3f}"


def format_rate(value: Decimal) -> str:
    return f"{value.quantize(_MONEY, rounding=ROUND_HALF_UP):.2f}"


def format_date(value: date | None) -> str:
    return value.strftime("%d-%b-%Y") if value else ""


def build_invoice_html(context: InvoicePdfContext) -> str:
    environment = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIRECTORY),
        autoescape=select_autoescape(("html", "xml")),
    )
    template = environment.get_template("invoice.html")
    css = (_TEMPLATE_DIRECTORY / "invoice.css").read_text(encoding="utf-8")
    template_version = context.template_version
    return template.render(
        invoice=context,
        template_version=TEMPLATE_VERSION,
        css=css,
        format_money=format_money,
        format_quantity=format_quantity,
        format_rate=format_rate,
        format_date=format_date,
        default_logo_data_uri=_DEFAULT_LOGO_DATA_URI,
    )


def render_invoice_pdf(context: InvoicePdfContext) -> PdfGenerationResult:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as error:
        raise RuntimeError("Python Playwright is required to generate invoice PDFs") from error

    html = build_invoice_html(context)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.emulate_media(media="print")
            pdf_bytes = page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
        finally:
            browser.close()
    return PdfGenerationResult(pdf_bytes=pdf_bytes, sha256=hashlib.sha256(pdf_bytes).hexdigest())
