import base64
import subprocess
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.invoice_pdf import (
    COPY_LABELS,
    TEMPLATE_VERSION,
    InvoicePdfContext,
    PdfLine,
    PdfParty,
    PdfSeller,
    build_invoice_html,
    build_purchase_order_context,
    render_invoice_pdf,
)


def test_versioned_invoice_template_contains_all_copies_and_reference_sections():
    context = InvoicePdfContext(
        seller=PdfSeller(
            legal_name="Demo Chemicals Private Limited",
            trade_name=None,
            logo_data_uri=None,
            address_lines=("Industrial Estate", "Hyderabad - 500001"),
            gstin="36AAAAA0000A1Z5",
            contact="billing@example.test",
            pickup_address="Industrial Estate, Hyderabad - 500001",
            mark_text="DCP",
        ),
        invoice_number="DEMO/2026-27/00001",
        invoice_date=date(2026, 8, 27),
        delivery_note_date=date(2026, 8, 28),
        payment_terms="On Delivery",
        po_number="PO-1",
        po_date=date(2026, 8, 26),
        irn="irn-demo-value",
        signed_qr_data=None,
        e_way_bill_number=None,
        e_way_bill_date=None,
        acknowledgement_number=None,
        acknowledgement_date=None,
        buyer=PdfParty(
            heading="Buyer Details",
            name="Buyer Example",
            address_lines=("Buyer Road", "Telangana - 500002"),
            gstin="36BBBBB0000B1Z5",
            contact="buyer@example.test",
        ),
        consignee=PdfParty(
            heading="Consignee / Shipping Details",
            name="Consignee Example",
            address_lines=("Ship Road", "Telangana - 500003"),
            gstin="36BBBBB0000B1Z5",
            contact=None,
            shipment_lines=("Mode of Shipment: ROAD", "Vehicle No: TS09AB1234"),
        ),
        transport_mode="ROAD",
        vehicle_number="TS09AB1234",
        vehicle_type=None,
        lr_number="LR-1",
        lr_date=date(2026, 8, 27),
        expected_delivery_date=None,
        lines=(
            PdfLine(
                serial_number=1,
                description="Chemical raw material",
                hsn_sac="29181590",
                quantity=Decimal("9798.000"),
                unit="KGS",
                base_rate=Decimal("30.00"),
                other_charge=Decimal("0.00"),
                discount=Decimal("0.00"),
                gst_rate=Decimal("18.00"),
                cess=Decimal("0.00"),
                amount=Decimal("346849.20"),
            ),
        ),
        total_quantity=Decimal("9798.000"),
        amount_in_words="Rupees Three Lakh Forty Six Thousand Eight Hundred Forty Nine Only",
        bank_lines=("Bank Name: Demo Bank", "A/C No.: 000000", "IFSC: DEMO0000001"),
        transporter_lines=("Transporter: Demo Transport", "GSTIN: 36CCCCC0000C1Z5"),
        tax_rows=(
            ("Taxable Value", Decimal("293940.00")),
            ("SGST", Decimal("26454.60")),
            ("CGST", Decimal("26454.60")),
            ("Cess Amount", Decimal("0.00")),
            ("Discount Value", Decimal("0.00")),
            ("Round Off Amount", Decimal("-0.20")),
        ),
        final_total=Decimal("346849.00"),
        terms=("Insurance at seller's account", "Payment by bank transfer only."),
        signed_by="Demo Chemicals Private Limited",
        generated_at=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
    )

    html = build_invoice_html(context)

    assert TEMPLATE_VERSION == "a4-invoice-v1"
    for label in COPY_LABELS:
        assert label in html
    for label in ("Tax Invoice", "IRN No.:", "Buyer Details", "Item Details", "Taxable Value", "Terms and Conditions:"):
        assert label in html
    assert "ACCORDD ORGANICS" not in html
    assert "PRISTINE BIOPHARMA" not in html
    assert "Delivery Note Date:" in html
    assert "28-Aug-2026" in html
    assert "Dispatched through:" in html
    assert html.count("By Canvatech") == len(COPY_LABELS)
    invoice_copy_css = html.split(".invoice-copy", 1)[1].split("}", 1)[0]
    assert "min-height: calc(297mm - 14mm)" in invoice_copy_css
    final_zone_css = html.split(".final-zone", 1)[1].split("}", 1)[0]
    assert "margin-top: auto" in final_zone_css
    canvatech_css = html.split(".canvatech-credit", 1)[1].split("}", 1)[0]
    assert "color: #111" in canvatech_css
    assert "font-weight: 700" in canvatech_css


def test_default_company_logo_is_rendered_in_each_seller_logo_slot():
    html = build_invoice_html(_fixture_context(1))
    logo_path = Path(__file__).parents[1] / "app" / "templates" / "invoice" / "v1" / "pb-logo-trimmed.png"
    logo_data_uri = "data:image/png;base64," + base64.b64encode(logo_path.read_bytes()).decode("ascii")

    assert html.count(logo_data_uri) == len(COPY_LABELS)
    assert html.count('class="default-seller-logo"') == len(COPY_LABELS)
    assert ".default-seller-logo" in html
    seller_header_css = html.split(".seller-header", 1)[1].split("}", 1)[0]
    assert "text-align: left" in seller_header_css
    default_logo_css = html.split(".seller-logo .default-seller-logo", 1)[1].split("}", 1)[0]
    assert "object-fit: contain" in default_logo_css
    assert "object-position: left center" in default_logo_css
    assert "#16a34a" in html.lower()
    assert "#007c78" in html.lower()
    assert "#84cc16" in html.lower()
    assert "#6d28d9" not in html.lower()
    assert "#ec4899" not in html.lower()
    assert "#b8f23d" not in html.lower()
    assert "#f8f5fc" not in html.lower()


def test_purchase_order_context_renders_a_separate_document_title_and_metadata():
    purchase_order = SimpleNamespace(
        branch_name="Hyderabad Branch",
        branch_gstin="36AAAAA0000A1Z5",
        order_date=date(2026, 8, 30),
        expected_delivery_date=date(2026, 9, 5),
        payment_terms="Advance before dispatch",
        purchase_order_number="PO-36AAAAA0000A1Z5/2026-27/00001",
        supplier_name="Raw Material Provider",
        supplier_gstin="36BBBBB0000B1Z5",
        supplier_phone="9000000000",
        supplier_email="supplier@example.test",
        supplier_address_line1="Industrial Supplier Road",
        supplier_address_line2="Warehouse 4",
        supplier_city="Hyderabad",
        supplier_state="Telangana",
        supplier_postal_code="500001",
        taxable_value=Decimal("1000.00"),
        cgst_amount=Decimal("90.00"),
        sgst_amount=Decimal("90.00"),
        igst_amount=Decimal("0.00"),
        cess_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        round_off=Decimal("0.00"),
        final_total=Decimal("1180.00"),
        amount_in_words="Rupees One Thousand One Hundred Eighty Only",
        lines=[
            SimpleNamespace(
                product_name="Sodium Hydroxide",
                description="Chemical raw material",
                hsn_sac="28151110",
                quantity=Decimal("10.000"),
                unit="KG",
                rate=Decimal("100.00"),
                other_charge=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                gst_rate=Decimal("18.00"),
                cess_amount=Decimal("0.00"),
                line_total=Decimal("1180.00"),
            )
        ],
    )
    branch = SimpleNamespace(
        address_line1="Branch Road",
        address_line2=None,
        city="Hyderabad",
        state="Telangana",
        postal_code="500001",
        phone="9000000001",
        email="branch@example.test",
    )
    company = SimpleNamespace(legal_name="Demo Chemicals Private Limited", trade_name="Demo Chemicals", logo_data_uri=None)

    html = build_invoice_html(
        build_purchase_order_context(
            purchase_order,
            branch=branch,
            company=company,
            generated_at=datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
        )
    )

    assert "Purchase Order" in html
    assert "PO No:" in html
    assert "PO Date:" in html
    assert "PO-36AAAAA0000A1Z5/2026-27/00001" in html
    assert "Computer Generated Purchase Order" in html
    assert html.count('class="default-seller-logo"') == 1


def _fixture_context(line_count: int, *, long_content: bool = False, interstate: bool = False) -> InvoicePdfContext:
    long_text = " with a deliberately long chemical specification that must wrap safely without clipping " * 4
    lines = tuple(
        PdfLine(
            serial_number=index,
            description=f"Chemical raw material {index}{long_text if long_content else ''}",
            hsn_sac="29181590",
            quantity=Decimal("10.000"),
            unit="KGS",
            base_rate=Decimal("30.00"),
            other_charge=Decimal("0.00"),
            discount=Decimal("0.00"),
            gst_rate=Decimal("18.00"),
            cess=Decimal("0.00"),
            amount=Decimal("354.00"),
        )
        for index in range(1, line_count + 1)
    )
    long_address = "Long Industrial Chemical Manufacturing Estate, Plot 123, Export Processing Zone, Hyderabad, Telangana - 500001"
    terms = (
        tuple(
            f"Term {index}: insurance, storage, quality, payment and transport conditions apply for this generated invoice."
            for index in range(1, 14)
        )
        if long_content
        else ("Insurance at seller's account", "Payment by bank transfer only." )
    )
    return InvoicePdfContext(
        seller=PdfSeller(
            legal_name="Demo Chemicals Private Limited",
            trade_name=None,
            logo_data_uri=None,
            address_lines=(long_address, long_address) if long_content else ("Industrial Estate", "Hyderabad - 500001"),
            gstin="36AAAAA0000A1Z5",
            contact="billing@example.test",
            pickup_address=long_address if long_content else "Industrial Estate, Hyderabad - 500001",
            mark_text="DCP",
        ),
        invoice_number=f"DEMO/{'2026-27'}/{line_count:05d}",
        invoice_date=date(2026, 8, 27),
        payment_terms="On Delivery",
        po_number="PO-1",
        po_date=date(2026, 8, 26),
        irn="irn-demo-value" if not long_content else None,
        signed_qr_data=None,
        e_way_bill_number="EWB-DEMO" if not long_content else None,
        e_way_bill_date=date(2026, 8, 27) if not long_content else None,
        acknowledgement_number="ACK-DEMO" if not long_content else None,
        acknowledgement_date=None,
        buyer=PdfParty(
            heading="Buyer Details",
            name="Buyer Example",
            address_lines=(long_address, long_address) if long_content else ("Buyer Road", "Telangana - 500002"),
            gstin="29BBBBB0000B1Z5" if interstate else "36BBBBB0000B1Z5",
            contact="buyer@example.test",
        ),
        consignee=PdfParty(
            heading="Consignee / Shipping Details",
            name="Consignee Example",
            address_lines=(long_address, long_address) if long_content else ("Ship Road", "Karnataka - 560003" if interstate else "Telangana - 500003"),
            gstin="29BBBBB0000B1Z5" if interstate else "36BBBBB0000B1Z5",
            contact=None,
            shipment_lines=("Mode of Shipment: ROAD", "Vehicle No: TS09AB1234", "Vehicle Type: Regular"),
        ),
        transport_mode="ROAD",
        vehicle_number="TS09AB1234",
        vehicle_type="Regular",
        lr_number="LR-1",
        lr_date=date(2026, 8, 27),
        expected_delivery_date=date(2026, 8, 28),
        lines=lines,
        total_quantity=Decimal(line_count * 10),
        amount_in_words="Rupees Three Hundred Fifty Four Only",
        bank_lines=("Bank Name: Demo Bank", "Branch Name: Main", "A/C No.: 000000", "IFSC: DEMO0000001"),
        transporter_lines=("Transporter: Demo Transport", "GSTIN: 36CCCCC0000C1Z5"),
        tax_rows=(
            (("Taxable Value", Decimal("300.00")), ("IGST", Decimal("54.00")))
            if interstate
            else (("Taxable Value", Decimal("300.00")), ("SGST", Decimal("27.00")), ("CGST", Decimal("27.00")))
        ),
        final_total=Decimal("354.00"),
        terms=terms,
        signed_by="Demo Chemicals Private Limited",
        generated_at=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    ("fixture_name", "line_count", "long_content", "interstate"),
    [
        ("one-item-cgst-sgst", 1, False, False),
        ("twenty-items-cgst-sgst", 20, False, False),
        ("eighty-items-cgst-sgst", 80, False, False),
        ("long-address-description-terms", 1, True, False),
        ("one-item-igst", 1, False, True),
    ],
)
def test_pdf_fixtures_render_to_a4_with_four_complete_copies(
    tmp_path, fixture_name, line_count, long_content, interstate
):
    result = render_invoice_pdf(
        _fixture_context(line_count, long_content=long_content, interstate=interstate)
    )
    pdf_path = tmp_path / f"{fixture_name}.pdf"
    pdf_path.write_bytes(result.pdf_bytes)
    info = subprocess.run(
        ["pdfinfo", str(pdf_path)], check=True, capture_output=True, text=True
    ).stdout
    metadata = dict(
        line.split(":", 1) for line in info.splitlines() if ":" in line
    )

    assert result.sha256 == __import__("hashlib").sha256(result.pdf_bytes).hexdigest()
    assert int(metadata["Pages"].strip()) >= 4
    page_size = metadata["Page size"].strip().split()
    assert 594 <= float(page_size[0]) <= 596
    assert 840 <= float(page_size[2]) <= 843
    assert page_size[-1] == "(A4)"
