from dataclasses import replace
from datetime import UTC, datetime
import subprocess

import pytest
from playwright.sync_api import sync_playwright

from app.models.master_records import Supplier
from app.models.purchase_order import PurchaseOrder
from app.services.invoice_pdf import build_invoice_html, build_purchase_order_context, build_reagent_purchase_order_context
from tests.test_financial_correctness import _purchase_order_payload, _address
from tests.test_reagent_purchase_orders import _reagent_payload


@pytest.mark.parametrize("kind", ["domestic", "reagent"])
def test_po_panels_share_saved_seller_and_separate_phone_email(client, auth_headers, staff_user, branch, company, db_session, kind, tmp_path):
    payload = _reagent_payload(client, auth_headers, staff_user, branch) if kind == "reagent" else _purchase_order_payload(branch)
    payload["supplier"].update(name="Selected Seller", phone="9876500000", email="seller@example.org")
    if kind == "domestic":
        payload["purchaser"] = {"name": "Separate Purchaser", "address": _address("Purchaser"), "phone": "9000000001", "email": "purchaser@example.org"}
    response = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=payload)
    assert response.status_code == 201, response.text
    order = db_session.get(PurchaseOrder, response.json()["id"])
    purchaser_name = order.purchaser_name
    consignee_details = order.consignee_details
    master = db_session.get(Supplier, order.supplier_id)
    master.name, master.phone, master.email = "Later Master", "1111111111", "later@example.org"
    master.address_line1 = "Later Address"
    db_session.commit()
    builder = build_reagent_purchase_order_context if kind == "reagent" else build_purchase_order_context
    context = builder(order, company=company, branch=branch, generated_at=datetime(2026, 10, 7, 12, tzinfo=UTC))
    assert context.buyer.heading == "Seller"
    assert context.consignee.heading == "Seller / Shipping Address"
    for party in (context.buyer, context.consignee):
        assert party.name == "Selected Seller"
        assert party.address_lines[0] == payload["supplier"]["address"]["address_line1"]
        assert party.gstin == payload["supplier"]["gstin"]
        assert party.pan == payload["supplier"]["pan"]
        assert party.contact == "9876500000"
        assert party.email == "seller@example.org"
    assert context.buyer.address_lines == context.consignee.address_lines
    assert context.buyer.state_code == context.consignee.state_code
    html = build_invoice_html(context)
    assert "Later Master" not in html and "Later Address" not in html
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 734, "height": 1100})
            page.emulate_media(media="print")
            page.set_content(html, wait_until="load")
            panels = page.locator(".invoice-copy").first.locator(".party-panel")
            assert panels.count() == 2
            for panel in panels.all():
                assert panel.locator(".party-heading").evaluate("el => getComputedStyle(el).fontWeight") == "700"
                assert panel.locator(".party-name").evaluate("el => getComputedStyle(el).fontWeight") == "700"
                assert panel.locator(".party-contact").inner_text() == "Contact: 9876500000"
                assert panel.locator(".party-email").inner_text() == "Email: seller@example.org"
            for phone, email in ((None, "seller@example.org"), ("9876500000", None), (None, None)):
                left = replace(context.buyer, contact=phone, email=email)
                right = replace(context.consignee, contact=phone, email=email)
                page.set_content(build_invoice_html(replace(context, buyer=left, consignee=right)), wait_until="load")
                assert page.locator(".party-contact").count() == (len(context.copy_labels) * 2 if phone else 0)
                assert page.locator(".party-email").count() == (len(context.copy_labels) * 2 if email else 0)
            page.set_content(html, wait_until="load")
            pdf = page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            browser.close()
    path = tmp_path / f"{kind}-seller-panels.pdf"
    path.write_bytes(pdf)
    info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
    pages = next(int(line.split(":", 1)[1]) for line in info.splitlines() if line.startswith("Pages:"))
    assert pages == len(context.copy_labels), info
    subprocess.run(["pdftoppm", "-f", "1", "-singlefile", "-scale-to", "1400", "-png", str(path), str(path.with_suffix(""))], check=True, capture_output=True)
    # A display correction must not rewrite purchaser/consignee transaction data.
    assert order.purchaser_name == purchaser_name
    assert order.consignee_details == consignee_details
