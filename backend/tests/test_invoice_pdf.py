import base64
import subprocess
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.invoice_pdf import (
    COPY_LABELS,
    REAGENT_BILL_TEMPLATE_VERSION,
    TEMPLATE_VERSION,
    InvoicePdfContext,
    PdfLine,
    PdfParty,
    PdfSeller,
    build_invoice_context,
    build_invoice_html,
    build_purchase_order_context,
    format_quantity,
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
            pan="BBBBB1234C",
        ),
        consignee=PdfParty(
            heading="Consignee / Shipping Details",
            name="Consignee Example",
            address_lines=("Ship Road", "Telangana - 500003"),
            gstin="36BBBBB0000B1Z5",
            contact="9876543210 | consignee@example.test",
            pan="CCCCC5678D",
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
                amount=Decimal("293940.00"),
            ),
        ),
        total_quantity=Decimal("9798.000"),
        amount_in_words="Rupees Three Lakh Forty Six Thousand Eight Hundred Forty Nine Only",
        bank_lines=("Bank Name: Demo Bank", "A/C No.: 000000", "IFSC: DEMO0000001"),
        bank_detail_rows=(
            ("Our Bank.", "PRISTINE BIOPHARMA"),
            ("Account No.", "ACC12345784"),
            ("IFSC Code.", "BB0K000234"),
            ("PAN Card No.", "BKOPM0025Q"),
        ),
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

    assert TEMPLATE_VERSION == "a4-invoice-v11"
    for label in COPY_LABELS:
        assert label in html
    for label in ("Tax Invoice", "Buyer Details", "Item Details", "Taxable Value", "Terms and Conditions:"):
        assert label in html
        assert "ACCORDD ORGANICS" not in html
    assert '<td class="right">2,93,940.00</td>' in html
    assert "3,46,849.20" not in html
    assert "PRISTINE BIOPHARMA" in html
    assert "Our Bank." in html
    assert "Bank Details" in html
    assert "ACC12345784" in html
    assert "BB0K000234" in html
    assert "BKOPM0025Q" in html
    assert "PAN:" in html
    assert "CCCCC5678D" in html
    assert "9876543210 | consignee@example.test" in html
    assert "Cess Amount" not in html
    assert "Discount Value" not in html
    assert 'class="amount-words-line"' in html
    assert "Total Amount in words:" in html
    assert "Rupees Three Lakh Forty Six Thousand Eight Hundred Forty Nine Only" in html
    assert html.index('class="summary-zone"') < html.index('class="amount-words-line"') < html.index('class="summary-details-row"') < html.index('class="total-quantity"') < html.index('class="tax-summary"')
    assert html.index('class="bank-details-footer"') < html.index('class="quantity-summary"')
    amount_words_css = html.split(".amount-words", 1)[1].split("}", 1)[0]
    assert "font-size: 9.4pt" in amount_words_css
    total_quantity_css = html.split(".total-quantity", 1)[1].split("}", 1)[0]
    assert "padding: 0 0 1.2mm" in total_quantity_css
    assert "text-align: right" in total_quantity_css
    summary_zone_css = html.split(".summary-zone", 1)[1].split("}", 1)[0]
    assert "display: block" in summary_zone_css
    assert "margin-top: 3mm" in summary_zone_css
    summary_details_css = html.split(".summary-details-row", 1)[1].split("}", 1)[0]
    assert "display: grid" in summary_details_css
    assert "width: 100%" in amount_words_css
    assert "All payments must be made via bank transfer only. Cash payments are not accepted." in html
    assert "The goods once sold can not be returned and/or exchanged." in html
    assert "All the Goods are to be checked at our works." in html
    assert "Weightment done at our location will be final for accounting purpose." in html
    assert '<th scope="col">Other Charge</th>' not in html
    assert '<th scope="col">Discount</th>' not in html
    assert '<th scope="col">Cess</th>' not in html
    assert '<th scope="col">Base Rate</th>' not in html
    assert '<th scope="col">Rate</th>' in html
    assert '<col style="width: 30%" />' in html
    assert html.count('<col style="width: 14%" />') == len(COPY_LABELS) * 2
    assert html.count('<col style="width: 12%" />') == len(COPY_LABELS)
    assert html.count('<col style="width: 6%" />') == len(COPY_LABELS)
    assert html.count('<col style="width: 7%" />') == len(COPY_LABELS)
    assert html.count('<col style="width: 17%" />') == len(COPY_LABELS)
    assert "Delivery Note Date:" in html
    assert "28-Aug-2026" in html
    assert "Dispatched through:" in html
    assert html.count('class="canvatech-prefix"') == len(COPY_LABELS)
    assert html.count('class="canvatech-name"') == len(COPY_LABELS)
    invoice_copy_css = html.split(".invoice-copy", 1)[1].split("}", 1)[0]
    assert "min-height: calc(297mm - 14mm)" in invoice_copy_css
    final_zone_css = html.split(".final-zone", 1)[1].split("}", 1)[0]
    assert "margin-top: auto" in final_zone_css
    canvatech_css = html.split(".canvatech-credit", 1)[1].split("}", 1)[0]
    assert "font-size: 10.8pt" in canvatech_css
    assert "text-align: left" in canvatech_css
    prefix_css = html.split(".canvatech-prefix", 1)[1].split("}", 1)[0]
    assert "color: #111" in prefix_css
    assert "font-weight: 400" in prefix_css
    name_css = html.split(".canvatech-name", 1)[1].split("}", 1)[0]
    assert "color: #111" in name_css
    assert "font-weight: 700" in name_css
    footer_details_css = html.split(".invoice-footer-details", 1)[1].split("}", 1)[0]
    assert "display: block" in footer_details_css
    invoice_footer_css = html.split(".invoice-footer", 1)[1].split("}", 1)[0]
    assert "border-top: 0.9mm solid var(--invoice-green)" in invoice_footer_css
    computer_generated_css = html.split(".computer-generated", 1)[1].split("}", 1)[0]
    assert "text-align: left" in computer_generated_css
    assert ".quantity-unit {\n  display: inline;" in html
    assert 'font-family: Arial, "Arial Narrow", Helvetica, sans-serif;' in html
    assert 'font-family: "Arial Narrow", Arial, Helvetica, sans-serif;' in html


def test_default_company_logo_is_rendered_in_each_seller_logo_slot():
    html = build_invoice_html(_fixture_context(1))
    logo_path = Path(__file__).parents[1] / "app" / "templates" / "invoice" / "v1" / "pb-logo-trimmed.png"
    logo_data_uri = "data:image/png;base64," + base64.b64encode(logo_path.read_bytes()).decode("ascii")

    assert html.count(logo_data_uri) == len(COPY_LABELS)
    assert html.count('class="default-seller-logo"') == len(COPY_LABELS)
    assert ".default-seller-logo" in html
    seller_header_css = html.split(".seller-header", 1)[1].split("}", 1)[0]
    assert "text-align: left" in seller_header_css
    assert "border: 0" in seller_header_css
    invoice_meta_css = html.split(".invoice-meta", 1)[1].split("}", 1)[0]
    assert "border: 0" in invoice_meta_css
    party_panel_css = html.split(".party-panel", 1)[1].split("}", 1)[0]
    assert "min-height: 40mm" in party_panel_css
    assert "height: auto" in party_panel_css
    bank_css = html.split(".bank-details-footer", 1)[1].split("}", 1)[0]
    assert "border-top" not in bank_css
    assert "color: #111" in bank_css
    assert "font-weight: 700" in bank_css
    bank_heading_css = html.split(".bank-details-heading", 1)[1].split("}", 1)[0]
    assert "color: #111" in bank_heading_css
    assert "margin: 0 0 1.2mm" in bank_heading_css
    bank_row_css = html.split(".bank-detail-row", 1)[1].split("}", 1)[0]
    assert "margin: 0 0 0.4mm" in bank_row_css
    assert "line-height: 1.15" in bank_row_css
    signature_css = html.split(".signature", 1)[1].split("}", 1)[0]
    assert "text-align: right" in signature_css
    signature_text_css = html.split(".signature p", 1)[1].split("}", 1)[0]
    assert "font-size: 8.8pt" in signature_text_css
    assert "font-weight: 600" in signature_text_css
    terms_heading_css = html.split(".terms-heading", 1)[1].split("}", 1)[0]
    assert "color: #111" in terms_heading_css
    assert "font-size: 9.2pt" in terms_heading_css
    assert "font-weight: 700" in terms_heading_css
    terms_css = html.split(".terms", 1)[1].split("}", 1)[0]
    assert "margin-top: 2.5mm" in terms_css
    assert "margin-bottom: 6mm" in terms_css
    assert "color: #111" in terms_css
    terms_list_block = html.split(".terms-list", 1)[1].split("}", 1)[0]
    assert "max-width: 81ch" in terms_list_block
    terms_list_css = html.split(".terms-list li", 1)[1].split("}", 1)[0]
    assert "line-height: 1" in terms_list_css
    item_heading_css = html.split(".invoice-flow .item-heading th", 1)[1].split("}", 1)[0]
    assert "#ffffff 0%" in item_heading_css
    assert "#fbfffc 42%" in item_heading_css
    assert "#e8f6ed 100%" in item_heading_css
    assert "rgba(255, 255, 255, 0.98)" in item_heading_css
    assert "inset 0 1.5mm 3mm var(--invoice-peacock-shadow)" in item_heading_css
    assert "color: #075e54" in item_heading_css
    assert "border: 1px solid #111" in item_heading_css
    assert "border-bottom: 1px solid #111" in item_heading_css
    assert "var(--invoice-lime)" not in item_heading_css
    items_body_css = html.split(".items-table tbody", 1)[1].split("}", 1)[0]
    assert "height: 64mm" in items_body_css
    item_cells_css = html.split(".invoice-flow .items-table tbody td", 1)[1].split("}", 1)[0]
    assert "border-top: 0" in item_cells_css
    assert "border-bottom: 0" in item_cells_css
    assert "padding: 0.25mm 1.4mm" in item_cells_css
    assert "line-height: 1" in item_cells_css
    first_item_row_css = html.split(".invoice-flow .items-table tbody tr:first-child td", 1)[1].split("}", 1)[0]
    assert "padding-top: 2.5mm" in first_item_row_css
    last_item_row_css = html.split(".invoice-flow .items-table tbody tr:last-child td", 1)[1].split("}", 1)[0]
    assert "border-bottom: 1px solid #111" in last_item_row_css
    assert 'class="invoice-copy short-copy invoice-page"' in html
    footer_css = html.split(".short-copy .invoice-footer", 1)[1].split("}", 1)[0]
    assert "position: absolute" in footer_css
    assert "bottom: 0" in footer_css
    signature_position_css = html.split(".short-copy .signature", 1)[1].split("}", 1)[0]
    assert "position: relative" in signature_position_css
    assert "top: -13mm" in signature_position_css
    party_heading_css = html.split(".party-heading", 1)[1].split("}", 1)[0]
    assert "#ffffff 0%" in party_heading_css
    assert "#fbfffc 42%" in party_heading_css
    assert "#e8f6ed 100%" in party_heading_css
    assert "rgba(255, 255, 255, 0.98)" in party_heading_css
    assert "color: #075e54" in party_heading_css
    assert "border-bottom: 1px solid #111" in party_heading_css
    assert "var(--invoice-lime)" not in party_heading_css
    assert "inset 0 1.5mm 3mm var(--invoice-peacock-shadow)" in party_heading_css
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


def test_all_item_table_headings_are_centered_in_the_rendered_layout():
    from playwright.sync_api import sync_playwright

    html = build_invoice_html(_fixture_context(1))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            heading_styles = page.locator(".items-table .item-heading th").evaluate_all(
                """headers => headers.map((header) => ({
                    textAlign: getComputedStyle(header).textAlign,
                    verticalAlign: getComputedStyle(header).verticalAlign,
                }))"""
            )
        finally:
            browser.close()

    assert heading_styles
    assert all(style == {"textAlign": "center", "verticalAlign": "middle"} for style in heading_styles)


def test_only_canvatech_name_uses_glossy_dark_black_footer_styling():
    from playwright.sync_api import sync_playwright

    html = build_invoice_html(_fixture_context(1))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            name_style = page.locator(".canvatech-name").first.evaluate(
                """element => ({
                    color: getComputedStyle(element).color,
                    fontWeight: getComputedStyle(element).fontWeight,
                    textShadow: getComputedStyle(element).textShadow,
                })"""
            )
            prefix_style = page.locator(".canvatech-prefix").first.evaluate(
                """element => ({
                    color: getComputedStyle(element).color,
                    fontWeight: getComputedStyle(element).fontWeight,
                    textShadow: getComputedStyle(element).textShadow,
                })"""
            )
        finally:
            browser.close()

    assert name_style["color"] == "rgb(17, 17, 17)"
    assert name_style["fontWeight"] == "700"
    assert name_style["textShadow"] != "none"
    assert "rgba(255, 255, 255" in name_style["textShadow"]
    assert prefix_style == {
        "color": "rgb(17, 17, 17)",
        "fontWeight": "400",
        "textShadow": "none",
    }


def test_quantity_display_omits_insignificant_trailing_zero_decimals():
    assert format_quantity(Decimal("8900.000")) == "8900"
    assert format_quantity(Decimal("10.500")) == "10.5"
    assert format_quantity(Decimal("10.005")) == "10.005"


def test_sales_invoice_item_amount_uses_taxable_value_and_summary_keeps_gst_total():
    class Stub(SimpleNamespace):
        def __getattr__(self, name):
            return None

    invoice = Stub(
        branch_name="Demo Seller",
        branch_gstin="36AAAAA0000A1Z5",
        invoice_number="PBPL/26-27/NO.00001",
        invoice_date=date(2026, 10, 1),
        buyer_name="Buyer",
        buyer_address_line1="Buyer Road",
        buyer_city="Hyderabad",
        buyer_state="Telangana",
        buyer_postal_code="500001",
        taxable_value=Decimal("1000.00"),
        cgst_amount=Decimal("90.00"),
        sgst_amount=Decimal("90.00"),
        igst_amount=Decimal("0.00"),
        cess_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        round_off=Decimal("0.00"),
        final_total=Decimal("1180.00"),
        amount_in_words="Rupees One Thousand One Hundred Eighty Only",
        lines=(
            Stub(
                description="Sodium Hydroxide",
                hsn_sac="28151110",
                quantity=Decimal("10.000"),
                unit="KG",
                rate=Decimal("100.00"),
                other_charge=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                taxable_value=Decimal("1000.00"),
                gst_rate=Decimal("18.00"),
                cess_amount=Decimal("0.00"),
                line_total=Decimal("1180.00"),
            ),
        ),
    )

    context = build_invoice_context(
        invoice,
        generated_at=datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc),
    )
    html = build_invoice_html(context)

    assert context.lines[0].amount == Decimal("1000.00")
    assert '<td class="right">1,000.00</td>' in html
    assert "1,180.00" in html


def test_reagent_pdf_context_preserves_manufacturer_name_snapshot():
    class Stub(SimpleNamespace):
        def __getattr__(self, name):
            return None

    invoice = Stub(
        document_type="reagent",
        branch_name="Demo Seller",
        branch_gstin="36AAAAA0000A1Z5",
        invoice_number="PBPL/2026-27/NO. 00001",
        invoice_date=date(2026, 10, 2),
        buyer_name="Research Lab",
        buyer_address_line1="Buyer Road",
        buyer_city="Hyderabad",
        buyer_state="Telangana",
        buyer_postal_code="500001",
        taxable_value=Decimal("1500.00"),
        cgst_amount=Decimal("135.00"),
        sgst_amount=Decimal("135.00"),
        igst_amount=Decimal("0.00"),
        cess_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        round_off=Decimal("0.00"),
        final_total=Decimal("1770.00"),
        amount_in_words="Rupees One Thousand Seven Hundred Seventy Only",
        lines=(
            Stub(
                product_name="Methanol",
                description="Laboratory reagent",
                manufacturer_name="Sigma Aldrich",
                manufacturer_code="SIG",
                manufacturer_product_code="M-100",
                part_no="M-100",
                hsn_sac="29051100",
                quantity=Decimal("1.000"),
                unit="kg",
                rate=Decimal("1500.00"),
                other_charge=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                discount_percent=Decimal("0.00"),
                taxable_value=Decimal("1500.00"),
                gst_rate=Decimal("18.00"),
                cess_amount=Decimal("0.00"),
                cgst_amount=Decimal("135.00"),
                sgst_amount=Decimal("135.00"),
                igst_amount=Decimal("0.00"),
                line_total=Decimal("1770.00"),
            ),
        ),
    )

    context = build_invoice_context(
        invoice,
        generated_at=datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc),
    )

    assert getattr(context.lines[0], "manufacturer_name", None) == "Sigma Aldrich"


def test_purchase_order_context_renders_a_separate_document_title_and_metadata():
    purchase_order = SimpleNamespace(
        branch_name="Hyderabad Branch",
        branch_gstin="36AAAAA0000A1Z5",
        branch_state_code="36",
        order_date=date(2026, 8, 30),
        expected_delivery_date=date(2026, 9, 5),
        payment_terms="Advance before dispatch",
        purchase_order_number="PO-36AAAAA0000A1Z5/2026-27/00001",
        supplier_name="Raw Material Provider",
        supplier_gstin="36BBBBB0000B1Z5",
        supplier_pan="BBOPM0123Z",
        supplier_phone="9000000000",
        supplier_email="supplier@example.test",
        supplier_address_line1="Industrial Supplier Road",
        supplier_address_line2="Warehouse 4",
        supplier_city="Hyderabad",
        supplier_state="Telangana",
        supplier_postal_code="500001",
        purchaser_name="Acme Manufacturing Private Limited",
        purchaser_gstin="36AACCA1234A1Z5",
        purchaser_pan="AACCA1234A",
        purchaser_phone="9000000002",
        purchaser_email="purchaser@example.test",
        purchaser_address_line1="Purchaser Industrial Estate",
        purchaser_address_line2="Building 7",
        purchaser_city="Hyderabad",
        purchaser_state="Telangana",
        purchaser_postal_code="500010",
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
                taxable_value=Decimal("1000.00"),
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
        state_code="36",
        postal_code="500001",
        phone="9000000001",
        email="branch@example.test",
        bank_name="Demo Bank",
        bank_branch_name="Main Branch",
        bank_account_name="PRISTINE BIOPHARMA",
        bank_account_number="ACC12345784",
        bank_ifsc_code="BCBM0000091",
        terms_body=None,
    )
    company = SimpleNamespace(legal_name="Demo Chemicals Private Limited", trade_name="Demo Chemicals", logo_data_uri=None, pan="BKOPM0025Q")
    bank_account = SimpleNamespace(
        bank_name="Demo Bank",
        branch_name="Main Branch",
        account_name="PRISTINE BIOPHARMA",
        account_number="ACC12345784",
        ifsc_code="BCBM0000091",
    )
    terms = SimpleNamespace(body="Payment by bank transfer only.\nGoods are subject to inspection.")

    context = build_purchase_order_context(
        purchase_order,
        branch=branch,
        company=company,
        bank_account=bank_account,
        terms=terms,
        generated_at=datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
    )
    html = build_invoice_html(context)

    assert context.lines[0].amount == Decimal("1000.00")
    assert '<td class="right">1,000.00</td>' in html
    assert "1,180.00" in html
    assert "Purchase Order" in html
    assert "PO No:" in html
    assert "PO Date:" in html
    assert "PO-36AAAAA0000A1Z5/2026-27/00001" in html
    assert "Computer Generated Purchase Order" in html
    assert "Sodium Hydroxide" in html
    assert "Chemical raw material" not in html
    assert html.count('class="default-seller-logo"') == 1
    assert html.count("Raw Material Provider") == 2
    assert html.count("Industrial Supplier Road") == 2
    assert "Acme Manufacturing Private Limited" not in html
    assert "Purchaser Industrial Estate" not in html
    assert "36AACCA1234A1Z5" not in html
    assert "BBOPM0123Z" in html
    assert html.count('Contact:</span> 9000000000') == 2
    assert html.count('Email:</span> supplier@example.test') == 2
    assert "Bank Details" in html
    assert "PRISTINE BIOPHARMA" in html
    assert "ACC12345784" in html
    assert "BCBM0000091" in html
    assert "BKOPM0025Q" in html
    assert '<th scope="col">Discount</th>' not in html
    assert "Discount Value" not in html
    assert "All payments must be made via bank transfer only." in html
    assert "Payment by bank transfer only." in html
    assert "Goods are subject to inspection." in html
    invoice_footer_css = html.split(".invoice-footer", 1)[1].split("}", 1)[0]
    assert "border-top: 0.9mm solid var(--invoice-green)" in invoice_footer_css
    party_heading_css = html.split(".party-heading", 1)[1].split("}", 1)[0]
    item_heading_css = html.split(".invoice-flow .item-heading th", 1)[1].split("}", 1)[0]
    for style in (party_heading_css, item_heading_css):
        assert "#ffffff 0%" in style
        assert "#fbfffc 42%" in style
        assert "#e8f6ed 100%" in style
        assert "rgba(255, 255, 255, 0.98)" in style
        assert "inset 0 1.5mm 3mm var(--invoice-peacock-shadow)" in style
    assert "inset 0 1.5mm 3mm var(--invoice-peacock-shadow)" in html
    assert ".invoice-flow .items-table tbody tr:first-child td" in html
    assert "padding-top: 2.5mm" in html


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
            amount=Decimal("300.00"),
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
            contact="9876543210 | consignee@example.test",
            pan="CCCCC5678D",
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
        bank_detail_rows=(
            ("Our Bank.", "PRISTINE BIOPHARMA"),
            ("Account No.", "ACC12345784"),
            ("IFSC Code.", "BB0K000234"),
            ("PAN Card No.", "BKOPM0025Q"),
        ),
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


def test_sales_invoice_meta_shows_only_approved_transport_fields_in_order():
    context = replace(
        _fixture_context(1),
        irn="IRN-SHOULD-NOT-RENDER",
        e_way_bill_number="EWB-SHOULD-NOT-RENDER",
        e_way_bill_date=date(2026, 8, 28),
        acknowledgement_number="ACK-SHOULD-NOT-RENDER",
        acknowledgement_date=date(2026, 8, 28),
    )

    html = build_invoice_html(context)
    meta_html = html.split('<div class="invoice-meta">', 1)[1].split('<div class="party-grid">', 1)[0]
    approved_labels = (
        "PO No:",
        "Invoice No:",
        "Invoice Date:",
        "Delivery Note Date:",
        "Dispatched through:",
        "Vehicle No.:",
        "LR No.:",
        "Payment Terms:",
    )

    for label in approved_labels:
        assert meta_html.count(label) == 1
    first_positions = [meta_html.index(label) for label in approved_labels]
    assert first_positions == sorted(first_positions)
    for hidden_label in ("IRN No.:", "PO Date:", "E-Way Bill No.:", "E-Way Bill Date:", "Ack. No.:", "Ack. Date:"):
        assert hidden_label not in meta_html


def test_short_sales_invoice_uses_42mm_table_and_one_page_per_copy(tmp_path):
    context = _fixture_context(1)
    result = render_invoice_pdf(context)
    pdf_path = tmp_path / "short-sales-invoice.pdf"
    pdf_path.write_bytes(result.pdf_bytes)
    info = subprocess.run(
        ["pdfinfo", str(pdf_path)], check=True, capture_output=True, text=True
    ).stdout
    metadata = {
        line.split(":", 1)[0]: line.split(":", 1)[1].strip()
        for line in info.splitlines()
        if ":" in line
    }

    assert int(metadata["Pages"]) == len(COPY_LABELS)

    html = build_invoice_html(context)
    assert html.count('class="items-table sales-items-table"') == len(COPY_LABELS)
    compact_table_css = html.split(
        ".short-copy .sales-items-table tbody", 1
    )[1].split("}", 1)[0]
    assert "height: 42mm" in compact_table_css

    purchase_order_html = build_invoice_html(
        replace(context, document_type="purchase_order")
    )
    reagent_html = build_invoice_html(replace(context, document_type="reagent"))
    assert 'class="items-table sales-items-table"' not in purchase_order_html
    assert 'class="items-table sales-items-table"' not in reagent_html


@pytest.mark.parametrize(
    ("fixture_name", "line_count", "long_content", "interstate"),
    [
        ("one-item-cgst-sgst", 1, False, False),
        ("six-items-cgst-sgst", 6, False, False),
        ("twenty-items-cgst-sgst", 20, False, False),
        ("eighty-items-cgst-sgst", 80, False, False),
        ("long-address-description-terms", 1, True, False),
        ("one-item-igst", 1, False, True),
    ],
)
def test_pdf_fixtures_render_to_a4_with_four_complete_copies(
    tmp_path, fixture_name, line_count, long_content, interstate
):
    if long_content:
        # This fixture combines 13 lengthy terms, doubled long postal blocks and
        # a very long item. They cannot all fit a single complete A4 page even
        # with one product; reject rather than restore a closing-only page.
        with pytest.raises(RuntimeError, match="fit.*A4"):
            render_invoice_pdf(_fixture_context(line_count, long_content=True))
        return
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


def test_reagent_bill_pdf_uses_its_versioned_item_columns(tmp_path):
    context = _fixture_context(1)
    reagent_context = replace(
        context,
        document_type="reagent",
        template_version=REAGENT_BILL_TEMPLATE_VERSION,
        lines=(replace(context.lines[0], part_no="RX-001", article_no="RX-001", discount_percent=Decimal("5.00"), amount=Decimal("285.00")),),
        amount_in_words="Rupees Three Hundred Thirty Six Only",
        tax_rows=(("Taxable Value", Decimal("285.00")), ("SGST", Decimal("25.65")), ("CGST", Decimal("25.65"))),
        final_total=Decimal("336.30"),
    )
    html = build_invoice_html(reagent_context)

    for heading in ("Sr. No.", "Item Description", "HSN/SAC", "GST", "Quantity", "Pack/Size", "Rate", "Disc %", "Amount"):
        assert f">{heading}</th>" in html
    assert html.count('class="items-table reagent-items-table"') == len(COPY_LABELS)
    assert html.count("a4-reagent-bill-v13") == 1
    assert html.count("IRN No.:") == len(COPY_LABELS)
    assert html.count("PO Date:") == len(COPY_LABELS)
    assert html.count("E-Way Bill No.:") == len(COPY_LABELS)
    assert html.count("Ack. No.:") == len(COPY_LABELS)
    assert html.count('<td class="center">1</td>') == len(COPY_LABELS)
    assert html.count("Artical No.: RX-001") == len(COPY_LABELS)
    assert html.count('class="item-discount-cell">5%') == len(COPY_LABELS)
    assert html.count('class="item-goods-amount">285.00</div>') == len(COPY_LABELS)
    assert "Part No." not in html
    assert '<th scope="col">Artical No.</th>' not in html
    assert '<th scope="col">Other Charge</th>' not in html
    assert '<th scope="col">Cess</th>' not in html
    for width in ("5%", "31%", "9%", "7%", "6%", "10%", "12%"):
        assert f'<col style="width: {width}" />' in html
    reagent_header_css = html.split(".reagent-items-table .item-heading th {", 1)[1].split("}", 1)[0]
    assert "padding: 2mm 0.5mm" in reagent_header_css
    reagent_quantity_css = html.split(".reagent-items-table .item-heading th:nth-child(5)", 1)[1].split("}", 1)[0]
    assert "white-space: nowrap" in reagent_quantity_css
    assert '<th scope="col">Per</th>' not in html

    result = render_invoice_pdf(reagent_context)
    pdf_path = tmp_path / "reagent-bill.pdf"
    pdf_path.write_bytes(result.pdf_bytes)
    info = subprocess.run(
        ["pdfinfo", str(pdf_path)], check=True, capture_output=True, text=True
    ).stdout
    metadata = {line.split(":", 1)[0]: line.split(":", 1)[1].strip() for line in info.splitlines() if ":" in line}
    assert int(metadata["Pages"]) >= len(COPY_LABELS)


def test_item_rows_show_product_name_secondary_metadata_and_split_gst():
    context = _fixture_context(1)
    line = replace(
        context.lines[0],
        description="Description must not replace the product name",
        product_name="Sodium Citrate",
        manufacturer_name="Sigma Aldrich",
        manufacturer_code="SIG",
        article_no="SIG-001",
        part_no="SIG-001",
        gst_rate=Decimal("5.00"),
        cgst_rate=Decimal("2.50"),
        sgst_rate=Decimal("2.50"),
        cgst_amount=Decimal("12.50"),
        sgst_amount=Decimal("12.50"),
        amount=Decimal("500.00"),
    )
    html = build_invoice_html(
        replace(
            context,
            document_type="reagent",
            template_version=REAGENT_BILL_TEMPLATE_VERSION,
            lines=(line,),
        )
    )

    assert html.count('class="item-product-name">Sodium Citrate</div>') == len(COPY_LABELS)
    assert "Description must not replace the product name" not in html
    assert html.count("Sigma Aldrich, Artical No.: SIG-001") == len(COPY_LABELS)
    assert "Manufacturer Code:" not in html
    assert html.count('class="item-tax-row">CGST 2.5%</div>') == len(COPY_LABELS)
    assert html.count('class="item-tax-row">SGST 2.5%</div>') == len(COPY_LABELS)
    assert html.count('class="item-tax-amount-row">12.50</div>') == len(COPY_LABELS) * 2
    description_layout_css = html.split(".item-description-layout", 1)[1].split("}", 1)[0]
    assert "display: flex" in description_layout_css
    assert "min-height: 17mm" in description_layout_css
    tax_row_css = html.split(".item-tax-row,", 1)[1].split("}", 1)[0]
    assert "text-align: right" in tax_row_css
    tax_breakdown_css = html.split(".item-tax-breakdown", 1)[1].split("}", 1)[0]
    assert "margin-top: auto" in tax_breakdown_css
    assert ".reagent-items-table .item-description {" in html
    reagent_description_css = html.split(".reagent-items-table .item-description {", 1)[1].split("}", 1)[0]
    assert "white-space: normal" in reagent_description_css
    assert "vertical-align: top" in reagent_description_css
