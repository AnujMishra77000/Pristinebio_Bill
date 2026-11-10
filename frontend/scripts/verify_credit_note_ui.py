"""Real browser Credit Note UI; intercept every API call, never client data."""
from copy import deepcopy
import json
import os
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

from billing_test_pdf import blank_a4_pdf
from verify_invoice_financial_year_ui import _mock_api
from verify_saved_bill_editing_ui import fixture

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3101")


def main():
    note = fixture("invoices", "credit_note")
    note["invoice_number"] = "PBPL/CN/2026-27/EDIT-101"
    final = {**deepcopy(note), "id": 102, "status": "pdf_generated", "pdf_storage_key": "saved.pdf", "invoice_number": "PBPL/CN/2026-27/FINAL-102"}
    address = {"address_line1": "Current master address", "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001"}
    supplier = {"id": 1, "branch_id": 1, "name": "Current supplier", "address": address, "is_active": True, "is_default": True}
    patches, unexpected, pdf_requests, errors = [], [], [], []

    def fulfill(route, value):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(value))

    def handle(route):
        parsed = urlsplit(route.request.url)
        path, method = parsed.path.removeprefix("/api/v1"), route.request.method
        if path in ("/auth/me", "/auth/csrf", "/companies/profile"):
            _mock_api(route)
        elif path == "/dashboard":
            fulfill(route, {"sales_invoice_count": 4, "reagent_invoice_count": 3, "domestic_oils_purchase_order_count": 2, "reagent_purchase_order_count": 1, "credit_note_count": 2})
        elif path == "/suppliers": fulfill(route, [supplier])
        elif path == "/suppliers/1": fulfill(route, supplier)
        elif path == "/manufacturers":
            fulfill(route, [{"id": 5, "branch_id": 1, "name": "Merck", "code": "MRK", "is_active": True}])
        elif path in ("/customers", "/products"): fulfill(route, [])
        elif path == "/invoices/register":
            assert parse_qs(parsed.query)["document_type"] == ["credit_note"]
            fulfill(route, {"items": [note, final], "total": 2, "page": 1, "page_size": 10})
        elif path in ("/invoices/101", "/invoices/102") and method == "GET":
            fulfill(route, note if path.endswith("101") else final)
        elif path == "/invoices/101" and method == "PATCH":
            body = route.request.post_data_json
            assert body["expected_version"] == note["version"]
            assert body["invoice_number_suffix"] == "EDIT-101"
            patches.append(body)
            note["version"] += 1
            note["lines"][0]["quantity"] = body["lines"][0]["quantity"]
            fulfill(route, note)
        elif path == "/invoices/preview": fulfill(route, {**note, "lines": []})
        elif path == "/invoices/101/preview-pdf":
            assert route.request.post_data_json["expected_version"] == note["version"]
            pdf_requests.append(path)
            route.fulfill(status=200, content_type="application/pdf", body=blank_a4_pdf())
        elif path == "/invoices/101/submit":
            note["status"] = "pending_approval"
            fulfill(route, note)
        elif path == "/invoices/101/approve":
            note["status"] = "approved"
            fulfill(route, note)
        elif path == "/invoices/101/generate-pdf":
            note["status"] = "pdf_generated"
            note["pdf_storage_key"] = "confirmed.pdf"
            fulfill(route, note)
        elif path in ("/invoices/101/pdf", "/invoices/102/pdf"):
            pdf_requests.append(path)
            route.fulfill(status=200, content_type="application/pdf", body=blank_a4_pdf())
        else:
            unexpected.append((method, path))
            route.abort()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/v1/**", handle)
        page.goto(BASE_URL)
        card = page.get_by_role("region", name="Saved bill registers").get_by_role("link", name="Credit Note", exact=False)
        expect(card).to_contain_text("2 bills")
        expect(card).to_have_attribute("href", "/bill-registers/credit-notes")
        card.click()
        draft_edit = page.get_by_role("link", name="Edit bill PBPL/CN/2026-27/EDIT-101", exact=True)
        expect(draft_edit).to_have_attribute("href", "/credit-notes?invoice=101")
        expect(page.get_by_role("link", name="Edit bill PBPL/CN/2026-27/FINAL-102", exact=True)).to_have_attribute("href", "/credit-notes?invoice=102&correction=1")
        draft_edit.click()
        expect(page.get_by_role("heading", name="Credit Note entry", exact=True)).to_be_visible()
        expect(page.get_by_label("Credit Note No.", exact=True)).to_have_value("EDIT-101")
        expect(page.get_by_test_id("invoice-number-prefix")).to_have_text("PBPL/CN/2026-27/")
        expect(page.get_by_label("Buyer/vendor name", exact=True)).to_have_value("Snapshot Buyer")
        expect(page.get_by_label("Consignee name", exact=True)).to_have_value("Snapshot Warehouse")
        expect(page.get_by_role("combobox", name="MFG / Manufacturer", exact=True)).to_have_value("5")
        expect(page.get_by_label("MFG Product Code / Part No.", exact=True)).to_have_value("ART-18")
        expect(page.get_by_label("Pack/Size", exact=True)).to_have_value("500 g")
        quantity = page.get_by_label("Quantity", exact=True)
        expect(quantity).to_have_value("1.000")
        quantity.fill("2.000")
        page.get_by_role("link", name="Credit notes", exact=True).click()
        page.get_by_role("link", name="Edit bill PBPL/CN/2026-27/EDIT-101", exact=True).click()
        expect(page.get_by_label("Quantity", exact=True)).to_have_value("2.000")
        panel = page.get_by_role("region", name="Bill submission", exact=True)
        panel.get_by_role("button", name="Preview", exact=True).click()
        expect(panel.locator("iframe")).to_have_count(1)
        assert len(patches) == 1 and patches[0]["lines"][0]["quantity"] == "2.000"
        assert patches[0]["lines"][0]["description"] == "Snapshot description"
        assert patches[0]["lines"][0]["manufacturer_id"] == 5
        assert patches[0]["lines"][0]["manufacturer_product_code"] == "ART-18"
        assert patches[0]["lines"][0]["pack_size"] == "500 g"
        panel.get_by_role("button", name="Confirm", exact=True).click()
        expect(panel.get_by_role("button", name="Download", exact=True)).to_be_enabled()
        expect(panel.get_by_role("button", name="Print", exact=True)).to_be_enabled()
        expect(page.get_by_label("Quantity", exact=True)).to_be_disabled()
        page.get_by_role("link", name="Credit notes", exact=True).click()
        page.get_by_role("button", name="View bill PBPL/CN/2026-27/FINAL-102", exact=True).click()
        view = page.get_by_role("region", name="Bill PDF view")
        expect(view.locator("iframe")).to_have_count(1)
        expect(view.get_by_role("button", name="Print", exact=True)).to_be_visible()
        view.get_by_role("button", name="Close view", exact=True).click()
        page.get_by_role("button", name="Print bill PBPL/CN/2026-27/FINAL-102", exact=True).click()
        expect(page.get_by_role("region", name="Bill PDF view").locator("iframe")).to_have_count(1)
        assert "/invoices/102/pdf" in pdf_requests
        assert not unexpected, unexpected
        assert not errors, errors
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        page.screenshot(path="/private/tmp/billing-credit-note-register-mobile.png", full_page=True)
        browser.close()
    print("Passed: Credit Note dashboard/register, snapshot Edit, retained navigation, versioned save, Preview/Confirm, View/Print and mobile width")


if __name__ == "__main__":
    main()
