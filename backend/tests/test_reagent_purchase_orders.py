from decimal import Decimal
from datetime import UTC, datetime
import base64
import subprocess

import pytest
from playwright.sync_api import Page, sync_playwright

from sqlalchemy import func, select

from app.models.master_records import Product, Purchaser, Supplier
from app.models.purchase_order import PurchaseOrder, PurchaseOrderRevision
from app.services.invoice_pdf import COPY_LABELS, REAGENT_PURCHASE_ORDER_TEMPLATE_VERSION, build_reagent_purchase_order_context, build_purchase_order_context, build_invoice_html, render_invoice_pdf
from tests.test_financial_correctness import _address, _purchase_order_payload
from tests.test_suppliers import supplier_payload


def _reagent_payload(client, auth_headers, user, branch):
    manufacturer = client.post(
        "/api/v1/manufacturers", headers=auth_headers(user),
        json={"branch_id": branch.id, "code": "MRK", "name": "Merck", "is_active": True},
    ).json()
    payload = _purchase_order_payload(branch)
    payload.update(
        document_type="reagent", place_of_supply_state_code="36",
        delivery_note_date="2026-10-04", transport_mode="Road",
        vehicle_number="TS09AB1234", vehicle_type="Truck", lr_number="LR-104",
        lr_date="2026-10-03", expected_delivery_date="2026-10-05",
        purchaser={"name": "Research Purchaser", "address": _address("Research Purchaser"), "pan": "ABCDE1234F", "phone": "9876543210", "is_active": True},
        consignee={"name": "Research Warehouse", "address": _address("Warehouse", address_line1="New Delivery Street"), "pan": "FGHIJ1234K", "phone": "9000000000", "is_active": True},
    )
    payload["lines"][0].update(
        product_name="Reagent Reference Material", manufacturer_id=manufacturer["id"],
        manufacturer_product_code="MRK-007", part_no="MRK-007", quantity="2.000",
        unit="GM", rate="100.0000", discount_percent="10.00", gst_rate="5.00",
    )
    return payload


def test_reagent_po_saves_decimal_totals_and_manufacturer_snapshots_in_separate_register(
    client, auth_headers, staff_user, branch, db_session
):
    payload = _reagent_payload(client, auth_headers, staff_user, branch)
    created = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=payload)
    assert created.status_code == 201, created.text
    po = created.json()
    assert po["document_type"] == "reagent"
    assert po["taxable_value"] == "180.00"
    assert po["cgst_amount"] == po["sgst_amount"] == "4.50"
    assert po["final_total"] == "189.00"
    line = po["lines"][0]
    assert line["manufacturer_name"] == "Merck"
    assert line["manufacturer_code"] == "MRK"
    assert line["part_no"] == "MRK-007"
    assert line["discount_percent"] == "10.00"
    assert line["unit"] == "g"
    assert po["consignee"]["name"] == "Research Warehouse"
    assert po["vehicle_number"] == "TS09AB1234"
    assert client.get("/api/v1/purchase-orders", headers=auth_headers(staff_user)).json() == []
    reagent_register = client.get("/api/v1/purchase-orders/register?document_type=reagent", headers=auth_headers(staff_user))
    assert reagent_register.json()["total"] == 1
    assert reagent_register.json()["items"][0]["id"] == po["id"]


def test_reagent_preview_is_read_only_and_matches_saved_and_approved_totals(client, auth_headers, staff_user, manager_user, branch, db_session):
    payload = _reagent_payload(client, auth_headers, staff_user, branch)
    payload["place_of_supply_state_code"] = "29"
    payload["freight_charges"] = "1.00"
    counts = lambda: tuple(db_session.scalar(select(func.count()).select_from(model)) for model in (Supplier, Purchaser, Product, PurchaseOrder))
    before = counts()
    preview = client.post("/api/v1/purchase-orders/preview", headers=auth_headers(staff_user), json=payload)
    assert preview.status_code == 200, preview.text
    assert counts() == before
    created = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=payload).json()
    assert created["cgst_amount"] == created["sgst_amount"] == "0.00"
    for field in ("taxable_value", "igst_amount", "round_off", "final_total"):
        assert created[field] == preview.json()[field]
    document_id = created["id"]
    assert client.post(f"/api/v1/purchase-orders/{document_id}/generate-pdf", headers=auth_headers(staff_user)).status_code == 409
    submitted = client.post(f"/api/v1/purchase-orders/{document_id}/submit", headers=auth_headers(staff_user), json={"expected_version": created["version"]})
    assert submitted.status_code == 200
    assert client.post(f"/api/v1/purchase-orders/{document_id}/approve", headers=auth_headers(staff_user)).status_code == 403
    approved = client.post(f"/api/v1/purchase-orders/{document_id}/approve", headers=auth_headers(manager_user), json={"expected_version": created["version"]})
    assert approved.status_code == 200, approved.text
    assert approved.json()["final_total"] == preview.json()["final_total"]
    assert client.patch(f"/api/v1/purchase-orders/{document_id}", headers=auth_headers(staff_user), json={"expected_version": 1, "reagent_details": payload}).status_code == 409


def test_reagent_idempotency_and_optimistic_amendments_preserve_history(client, auth_headers, staff_user, admin_user, branch, db_session):
    payload = _reagent_payload(client, auth_headers, staff_user, branch)
    headers = {**auth_headers(staff_user), "Idempotency-Key": "reagent-po-save-1"}
    created = client.post("/api/v1/purchase-orders", headers=headers, json=payload).json()
    replay = client.post("/api/v1/purchase-orders", headers=headers, json=payload)
    assert replay.status_code == 200 and replay.json()["id"] == created["id"]
    assert client.post("/api/v1/purchase-orders", headers=headers, json={**payload, "payment_terms": "Changed"}).status_code == 409
    document_id = created["id"]
    changed = {**payload, "consignee": {**payload["consignee"], "name": "New Warehouse"}}
    changed["lines"] = [{**payload["lines"][0], "quantity": "3.000"}]
    missing_version = client.patch(f"/api/v1/purchase-orders/{document_id}", headers=auth_headers(staff_user), json={"reagent_details": changed})
    assert missing_version.status_code == 422
    edited = client.patch(f"/api/v1/purchase-orders/{document_id}", headers=auth_headers(staff_user), json={"expected_version": 1, "reagent_details": changed})
    assert edited.status_code == 200, edited.text
    assert edited.json()["final_total"] == "284.00"
    assert client.patch(f"/api/v1/purchase-orders/{document_id}", headers=auth_headers(staff_user), json={"expected_version": 1, "reagent_details": payload}).status_code == 409
    assert client.post(f"/api/v1/purchase-orders/{document_id}/submit", headers=auth_headers(staff_user), json={"expected_version": 2}).status_code == 200
    assert client.post(f"/api/v1/purchase-orders/{document_id}/approve", headers=auth_headers(admin_user), json={"expected_version": 2}).status_code == 200
    stored = db_session.get(PurchaseOrder, document_id)
    stored.pdf_storage_key = "old-file.pdf"
    db_session.commit()
    amended = client.post(f"/api/v1/purchase-orders/{document_id}/amend", headers=auth_headers(staff_user), json={"expected_version": 2, "reason": "Correct article quantity"})
    assert amended.status_code == 200 and amended.json()["pdf_storage_key"] is None
    revisions = list(db_session.scalars(select(PurchaseOrderRevision).where(PurchaseOrderRevision.purchase_order_id == document_id).order_by(PurchaseOrderRevision.revision)))
    assert revisions[0].snapshot["lines"][0]["quantity"] == "2.000"
    assert revisions[1].snapshot["document"]["consignee_details"]["name"] == "New Warehouse"
    assert revisions[2].snapshot["document"]["pdf_storage_key"] == "old-file.pdf"


@pytest.mark.parametrize("invalid", ["missing_manufacturer", "missing_place_of_supply", "invalid_unit", "excess_precision", "discount"])
def test_reagent_po_rejects_invalid_inputs(client, auth_headers, staff_user, branch, invalid):
    payload = _reagent_payload(client, auth_headers, staff_user, branch)
    if invalid == "missing_manufacturer": payload["lines"][0].pop("manufacturer_id")
    if invalid == "missing_place_of_supply": payload.pop("place_of_supply_state_code")
    if invalid == "invalid_unit": payload["lines"][0]["unit"] = "BOX"
    if invalid == "excess_precision": payload["lines"][0]["quantity"] = "1.0004"
    if invalid == "discount": payload["lines"][0]["discount_percent"] = "101.00"
    response = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=payload)
    assert response.status_code == 422, response.text


def test_reagent_po_blocks_inactive_manufacturer_and_unauthorized_profile(client, auth_headers, staff_user, admin_user, branch, other_branch, db_session):
    payload = _reagent_payload(client, auth_headers, staff_user, branch)
    assert client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json={**payload, "branch_id": other_branch.id}).status_code == 403
    disabled = client.patch(f"/api/v1/manufacturers/{payload['lines'][0]['manufacturer_id']}", headers=auth_headers(admin_user), json={"is_active": False})
    assert disabled.status_code == 200
    assert client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=payload).status_code == 422


def test_reagent_context_reuses_columns_and_keeps_domestic_format(client, auth_headers, staff_user, branch, company, db_session):
    payload = _reagent_payload(client, auth_headers, staff_user, branch)
    response = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=payload)
    order = db_session.get(PurchaseOrder, response.json()["id"])
    context = build_reagent_purchase_order_context(order, company=company, branch=branch, generated_at=datetime.now(UTC))
    assert context.template_version == REAGENT_PURCHASE_ORDER_TEMPLATE_VERSION
    assert context.copy_labels == ("Purchase Order",)
    assert context.buyer.heading == "Seller"
    assert context.document_title == "Purchase Order"
    assert context.buyer.name == order.supplier_name
    assert context.consignee.name == order.supplier_name
    assert context.consignee.pan == "FGHIJ1234K"
    assert context.consignee.contact == "9000000000"
    assert context.lines[0].manufacturer_name == "Merck"
    assert context.lines[0].article_no == "MRK-007"
    html = build_invoice_html(context)
    assert '<div class="invoice-title">Purchase Order</div>' in html and "reagent-items-table" in html
    assert html.count("All payments must be made via bank transfer only. Cash payments are not accepted.") == 1
    assert '<div class="reagent-po-final-block">' in html
    assert "Merck" in html and "MRK-007" in html
    domestic = build_purchase_order_context(order, company=company, branch=branch, generated_at=datetime.now(UTC))
    assert domestic.copy_labels == ("Purchase Order",)
    assert domestic.document_type == "purchase_order" and domestic.show_discounts is False
    assert '<div class="reagent-po-final-block">' not in build_invoice_html(domestic)


def test_reagent_po_pdf_shows_selected_saved_supplier_snapshot(client, auth_headers, staff_user, branch, company, db_session):
    saved_supplier = supplier_payload(branch.id, "Selected Reagent Supplier")
    saved_supplier.update(pan="ABCDE1234F", phone="9876500000", email="supplier@example.org")
    created_supplier = client.post("/api/v1/suppliers", headers=auth_headers(staff_user), json=saved_supplier)
    assert created_supplier.status_code == 201, created_supplier.text

    payload = _reagent_payload(client, auth_headers, staff_user, branch)
    payload.pop("supplier")
    payload["supplier_id"] = created_supplier.json()["id"]
    created = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=payload)
    assert created.status_code == 201, created.text
    order = db_session.get(PurchaseOrder, created.json()["id"])
    master = db_session.get(Supplier, created_supplier.json()["id"])
    master.name = "Later Changed Supplier Master"
    master.address_line1 = "Later Changed Road"
    db_session.commit()
    context = build_reagent_purchase_order_context(order, company=company, branch=branch, generated_at=datetime.now(UTC))
    supplier = context.buyer
    assert supplier.heading == "Seller"
    assert supplier.name == "Selected Reagent Supplier"
    assert supplier.address_lines == ("Industrial Supplier Road", "Warehouse 4", "Hyderabad, Telangana - 500001")
    assert supplier.gstin == "36ABCDE1234F1Z5"
    assert supplier.state_code == "36"
    assert supplier.pan == "ABCDE1234F"
    assert supplier.contact == "9876500000" and supplier.email == "supplier@example.org"
    assert context.consignee.name == "Selected Reagent Supplier"
    html = build_invoice_html(context)
    assert '<h2 class="party-heading">Seller</h2>' in html
    assert "Selected Reagent Supplier" in html and "Industrial Supplier Road" in html
    assert "State Code:</span> 36" in html


def test_reagent_pdf_api_stores_metadata_and_reuses_approved_document(client, auth_headers, staff_user, manager_user, branch, monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.services.invoice_pdf import PdfGenerationResult
    import hashlib
    payload = _reagent_payload(client, auth_headers, staff_user, branch)
    created = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=payload).json()
    document_id = created["id"]
    assert client.post(f"/api/v1/purchase-orders/{document_id}/submit", headers=auth_headers(staff_user), json={"expected_version": 1}).status_code == 200
    assert client.post(f"/api/v1/purchase-orders/{document_id}/approve", headers=auth_headers(manager_user), json={"expected_version": 1}).status_code == 200
    calls = []
    pdf = b"%PDF-test-reagent-purchase-order"
    def renderer(context):
        calls.append(context)
        assert context.document_title == "Purchase Order"
        return PdfGenerationResult(pdf, hashlib.sha256(pdf).hexdigest())
    monkeypatch.setattr("app.api.v1.purchase_orders.render_purchase_order_pdf", renderer)
    monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(tmp_path))
    generated = client.post(f"/api/v1/purchase-orders/{document_id}/generate-pdf", headers=auth_headers(manager_user))
    assert generated.status_code == 200, generated.text
    result = generated.json()
    assert result["pdf_sha256"] == hashlib.sha256(pdf).hexdigest()
    assert result["pdf_template_version"] == REAGENT_PURCHASE_ORDER_TEMPLATE_VERSION
    assert result["pdf_generated_by_id"] == manager_user.id and result["pdf_generated_at"]
    assert result["status"] == "approved"
    assert client.post(f"/api/v1/purchase-orders/{document_id}/generate-pdf", headers=auth_headers(manager_user)).status_code == 200
    assert len(calls) == 1
    downloaded = client.get(f"/api/v1/purchase-orders/{document_id}/pdf", headers=auth_headers(staff_user))
    assert downloaded.status_code == 200 and downloaded.content == pdf


@pytest.mark.parametrize("line_count,interstate", [(1, False), (20, True)])
def test_reagent_po_pdf_fixtures(client, auth_headers, staff_user, branch, company, db_session, tmp_path, line_count, interstate, monkeypatch):
    payload = _reagent_payload(client, auth_headers, staff_user, branch)
    if interstate: payload["place_of_supply_state_code"] = "29"
    payload["lines"] = [{**payload["lines"][0], "product_name": f"Reference Reagent {index + 1}"} for index in range(line_count)]
    response = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=payload)
    assert response.status_code == 201, response.text
    order = db_session.get(PurchaseOrder, response.json()["id"])
    branch.bank_account_name = "Example Laboratory"
    branch.bank_account_number = "TEST000123"
    branch.bank_ifsc_code = "TEST0000001"
    branch.terms_body = "Payment by bank transfer only.\nGoods must be checked on delivery."
    context = build_reagent_purchase_order_context(order, company=company, branch=branch, generated_at=datetime(2026, 10, 3, 12, 0, tzinfo=UTC))
    rendered = []
    chromium_pdf = Page.pdf

    def capture_print_layout(page, *args, **kwargs):
        rendered.append(page.content())
        return chromium_pdf(page, *args, **kwargs)

    monkeypatch.setattr(Page, "pdf", capture_print_layout)
    result = render_invoice_pdf(context)
    output = tmp_path / f"reagent-po-{line_count}.pdf"
    output.write_bytes(result.pdf_bytes)
    output.with_suffix(".html").write_text(rendered[0], encoding="utf-8")
    info = subprocess.run(["pdfinfo", str(output)], check=True, capture_output=True, text=True).stdout
    metadata = dict(line.split(":", 1) for line in info.splitlines() if ":" in line)
    page_count = int(metadata["Pages"].strip())
    assert page_count == ((line_count + 3) // 4)
    assert "(A4)" in metadata["Page size"]
    # Assert the measured-fit layout actually passed to Chromium, not the
    # unnormalized HTML with nominal empty-space reservations.
    html = rendered[0]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.emulate_media(media="print")
            page.set_content(html, wait_until="load")
            placements = page.locator(".reagent-po-final-block").evaluate_all("""blocks => blocks.map(block => {
                const bounds = block.getBoundingClientRect();
                const copy = block.closest('.invoice-copy').getBoundingClientRect();
                const terms = block.querySelector('.terms').getBoundingClientRect();
                const signature = block.querySelector('.signature').getBoundingClientRect();
                const footer = block.querySelector('.invoice-footer').getBoundingClientRect();
                const summary = block.querySelector('.summary-zone').getBoundingClientRect();
                return {
                    termsNearBottom: terms.bottom > bounds.bottom - 120,
                    signatureNearBottom: signature.bottom > bounds.bottom - 120,
                    sameBottomRow: Math.abs(terms.bottom - signature.bottom) < 12,
                    termsLeftOfSignature: terms.right <= signature.left + 1,
                    belowSummary: Math.min(terms.top, signature.top) >= summary.bottom - 1,
                    aboveFooter: Math.max(terms.bottom, signature.bottom) <= footer.top + 1,
                    footerAtBottom: Math.abs(footer.bottom - bounds.bottom) < 4,
                    fitsCopy: footer.bottom <= copy.bottom + 1,
                };
            })""")
        finally:
            browser.close()
    assert len(placements) == page_count
    assert all(all(placement.values()) for placement in placements), placements
    for label in context.copy_labels: assert label in html
    for expected in ('<div class="invoice-title">Purchase Order</div>', "Merck", "MRK-007", "PO Supplier", "FGHIJ1234K", "9000000000", "TEST000123", "Payment by bank transfer only.", f"Reference Reagent {line_count}"): assert expected in html
    assert result.sha256 and len(result.sha256) == 64
    subprocess.run(["pdftoppm", "-scale-to", "1400", "-png", str(output), str(output.with_suffix(""))], check=True, capture_output=True)
    assert list(tmp_path.glob(f"reagent-po-{line_count}-*.png"))
    # DOM positions/text extraction miss Chromium paint clipping after a page
    # break. The actual final sheet must paint its green footer near the bottom.
    closing_page = tmp_path / f"reagent-po-{line_count}-{str(page_count).zfill(len(str(page_count)))}.png"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            source = "data:image/png;base64," + base64.b64encode(closing_page.read_bytes()).decode()
            has_footer = page.evaluate("""async source => {
                const img = new Image(); img.src = source; await img.decode();
                const canvas = document.createElement('canvas'); canvas.width = img.width; canvas.height = img.height;
                const ctx = canvas.getContext('2d'); ctx.drawImage(img, 0, 0);
                const start = Math.floor(img.height * 0.85);
                const data = ctx.getImageData(0, start, img.width, img.height - start).data;
                let green = 0;
                for (let i = 0; i < data.length; i += 4) {
                    if (data[i] < 70 && data[i+1] > 120 && data[i+1] > data[i+2] * 1.4) green++;
                }
                return green > img.width;
            }""", source)
        finally:
            browser.close()
    assert has_footer, "Final PDF sheet clipped the bottom footer despite valid DOM positions"
