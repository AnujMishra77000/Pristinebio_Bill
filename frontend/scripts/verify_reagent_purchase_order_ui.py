"""Browser regression against a built frontend, using isolated API fixtures.

FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_reagent_purchase_order_ui.py
Real API calculations, permissions and persistence are tested by backend tests.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
from verify_invoice_financial_year_ui import _mock_api
from billing_test_pdf import blank_a4_pdf

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")
address = {"name": "Research Company", "address_line1": "Laboratory Road", "address_line2": None, "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001"}
party = {"id": 1, "branch_id": 1, "name": "Research Company", "gstin": None, "pan": "ABCDE1234F", "email": "accounts@example.test", "phone": "9000000000", "address": address, "is_active": True}
totals = {"taxable_value": "180.00", "cgst_amount": "4.50", "sgst_amount": "4.50", "igst_amount": "0.00", "cess_amount": "0.00", "unrounded_total": "189.00", "round_off": "0.00", "final_total": "189.00", "amount_in_words": "Rupees One Hundred Eighty Nine Only"}


def main():
    attempts = []
    documents = []
    conflict_once = [True]
    errors = []

    def fulfill(route, payload, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    def handle(route):
        path = urlparse(route.request.url).path.removeprefix("/api/v1")
        method = route.request.method
        if path == "/suppliers": fulfill(route, [
            {**party, "name": "Default Supplier", "is_default": True},
            {**party, "id": 2, "name": "Selected Reagent Supplier", "gstin": "36ABCDE1234F1Z5", "pan": "ABCDE1234F", "phone": "9876500000", "email": "supplier@example.org", "is_default": False,
             "address": {**address, "address_line1": "Industrial Supplier Road", "address_line2": "Warehouse 4"}},
        ])
        elif path == "/purchasers": fulfill(route, [party])
        elif path == "/manufacturers": fulfill(route, [{"id": 5, "branch_id": 1, "code": "MRK", "name": "Merck", "is_active": True}])
        elif path == "/products": fulfill(route, [{"id": 7, "branch_id": 1, "name": "Reference Reagent", "description": "Reference description", "hsn_sac": "29181590", "unit": "kg", "base_rate": "0.00", "gst_rate": "5.00", "cess_rate": "0.00", "manufacturer_id": None, "is_active": True}])
        elif path == "/purchase-orders/register": fulfill(route, {"items": documents, "total": len(documents), "page": 1, "page_size": 10})
        elif path == "/purchase-orders/preview": fulfill(route, {**totals, "lines": [{**route.request.post_data_json["lines"][0], **totals, "line_total": "189.00"}]})
        elif path == "/purchase-orders" and method == "POST":
            attempts.append((route.request.headers.get("idempotency-key"), route.request.post_data_json))
            if route.request.post_data_json["purchase_order_number"] == "EXISTING-001":
                fulfill(route, {"detail": {"code": "duplicate_po_number", "field": "purchase_order_number", "message": "This PO No. is already in use. Enter a different number."}}, 409)
            elif len(attempts) == 2: fulfill(route, {"detail": "Temporary save failure; retry"}, 503)
            else:
                payload = route.request.post_data_json
                assert payload["document_type"] == "reagent"
                assert not {"purchaser", "purchaser_id", "save_purchaser_for_future"}.intersection(payload)
                assert payload["supplier_id"] == 2
                assert payload["purchase_order_number"] == "CLIENT/REAGENT-0042"
                assert payload["lines"][0]["manufacturer_id"] == 5
                assert payload["lines"][0]["part_no"] == "MRK-007"
                assert payload["consignee"] is None
                order = {**payload, **totals, "id": 101, "branch_id": 1, "supplier_id": 2, "purchaser_id": 1, "created_by_id": 1, "supplier_name": "Selected Reagent Supplier", "supplier_gstin": "36ABCDE1234F1Z5", "supplier_pan": "ABCDE1234F", "supplier_phone": "9876500000", "supplier_email": "supplier@example.org", "supplier_address_line1": "Industrial Supplier Road", "supplier_address_line2": "Warehouse 4", "supplier_city": "Hyderabad", "supplier_state": "Telangana", "supplier_state_code": "36", "supplier_postal_code": "500001", "purchase_order_number": payload["purchase_order_number"], "status": "draft", "version": 1, "pdf_storage_key": None, "submitted_revision": None, "approved_revision": None,
                         **{f"purchaser_{key}": value for key, value in party.items() if key in ("name", "gstin", "pan", "email", "phone")},
                         **{f"purchaser_{key}": value for key, value in address.items() if key != "name"},
                         "lines": [{**payload["lines"][0], "id": 1, "product_id": 7, "product_name": "Reference Reagent", "manufacturer_name": "Merck", "manufacturer_code": "MRK", "sort_order": 1, **totals, "line_total": "189.00"}]}
                documents.append(order); fulfill(route, order, 201)
        elif path == "/purchase-orders/101" and method == "PATCH":
            if conflict_once[0]: conflict_once[0] = False; fulfill(route, {"detail": {"code": "version_conflict", "message": "Changed by another user", "current_version": 2}}, 409)
            else: documents[0]["version"] += 1; fulfill(route, documents[0])
        elif path == "/purchase-orders/101" and method == "GET": fulfill(route, documents[0])
        elif path.startswith("/purchase-orders/101/"):
            operation = path.rsplit("/", 1)[-1]
            if operation in ("preview-pdf", "pdf"):
                route.fulfill(status=200, content_type="application/pdf", body=blank_a4_pdf())
                return
            if operation == "submit": documents[0].update(status="pending_approval", submitted_revision=documents[0]["version"])
            elif operation == "approve": documents[0].update(status="approved", approved_revision=documents[0]["version"])
            elif operation == "generate-pdf": documents[0].update(pdf_storage_key="reagent-test.pdf", pdf_sha256="a" * 64, pdf_template_version="a4-reagent-purchase-order-v2")
            fulfill(route, documents[0])
        else: _mock_api(route)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(8000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/v1/**", handle)
        page.goto(f"{BASE_URL}/reagent-purchase-orders")
        expect(page.get_by_role("heading", name="Reagent purchase order", exact=True)).to_be_visible()
        expect(page.get_by_role("heading", name="Seller", exact=True)).to_be_visible()
        page.get_by_label("Search seller", exact=True).fill("Selected")
        page.get_by_label("Saved seller", exact=True).select_option("2")
        supplier_details = page.get_by_role("region", name="Seller / Shipping Address")
        for value in ("Selected Reagent Supplier", "Industrial Supplier Road", "Warehouse 4", "State code", "36ABCDE1234F1Z5", "ABCDE1234F", "9876500000", "supplier@example.org"):
            expect(supplier_details).to_contain_text(value)
        page.get_by_label("PO No.", exact=True).fill("existing-001")
        expect(page.get_by_label("Consignee same as purchaser", exact=True)).to_have_count(0)
        page.get_by_label("Saved product (optional)", exact=True).select_option("7")
        page.get_by_label("Manufacturer", exact=True).select_option("5")
        page.get_by_label("Article No.", exact=True).fill("MRK-007")
        page.get_by_label("Pack/Size", exact=True).fill("500 g")
        page.get_by_label("Quantity", exact=True).fill("2.000")
        page.get_by_label("Rate", exact=True).fill("100.0000")
        page.get_by_label("Per / unit", exact=True).select_option("g")
        page.get_by_label("Disc %", exact=True).fill("10.00")
        expect(page.get_by_text("Goods amount ₹180.00", exact=True)).to_be_visible()
        page.get_by_role("button", name="Save reagent purchase order", exact=True).click()
        expect(page.locator("#purchase_order_number-error")).to_have_text("This PO No. is already in use. Enter a different number.")
        page.get_by_label("PO No.", exact=True).fill("client/reagent-0042")
        page.get_by_role("button", name="Save reagent purchase order", exact=True).click()
        expect(page.get_by_role("alert").filter(has_text="Temporary save failure")).to_be_visible()
        expect(page.get_by_label("Article No.", exact=True)).to_have_value("MRK-007")
        expect(page.get_by_label("PO No.", exact=True)).to_have_value("CLIENT/REAGENT-0042")
        expect(page.get_by_label("Pack/Size", exact=True)).to_have_value("500 g")
        page.get_by_role("button", name="Save reagent purchase order", exact=True).click()
        expect(page.get_by_role("button", name="Save reagent PO changes", exact=True)).to_be_visible()
        expect(page.get_by_role("region", name="Seller / Shipping Address")).to_contain_text("Industrial Supplier Road")
        expect(page.get_by_label("Search seller", exact=True)).to_have_count(0)
        expect(page.get_by_label("Saved seller", exact=True)).to_be_disabled()
        assert len(attempts) == 3 and attempts[0][0] != attempts[1][0] and attempts[1] == attempts[2]
        page.get_by_label("Payment terms", exact=True).fill("45 days")
        page.get_by_role("button", name="Save reagent PO changes", exact=True).click()
        expect(page.get_by_role("button", name="Reload latest revision", exact=True)).to_be_visible()
        page.on("dialog", lambda dialog: dialog.accept())
        page.get_by_role("button", name="Reload latest revision", exact=True).click()
        expect(page.get_by_label("Payment terms", exact=True)).to_have_value("30 days")
        expect(page.get_by_label("PO No.", exact=True)).to_have_value("CLIENT/REAGENT-0042")
        panel = page.get_by_role("region", name="Bill submission", exact=True)
        panel.get_by_role("button", name="Preview", exact=True).click()
        expect(panel.locator('iframe[title="Bill PDF preview"]')).to_have_count(1)
        panel.get_by_role("button", name="Confirm", exact=True).click()
        expect(panel.get_by_role("button", name="Download", exact=True)).to_be_enabled()
        expect(panel.get_by_role("button", name="Print", exact=True)).to_be_enabled()
        page.get_by_role("button", name="Start new order", exact=True).click()
        expect(page.get_by_label("Search seller", exact=True)).to_have_value("")
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        output = Path(os.environ.get("UI_SCREENSHOT_PATH", "/private/tmp/reagent-po-ui.png"))
        page.screenshot(path=str(output), full_page=True)
        assert not errors, errors
        browser.close()
        print("Reagent PO UI: seller-only entry, independent manufacturer/product, retry idempotency, conflict recovery, approval/PDF actions and mobile width passed.")


if __name__ == "__main__": main()
