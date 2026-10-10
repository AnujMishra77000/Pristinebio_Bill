"""Domestic PO manual number, field-error and retry regression on built UI.

Uses isolated API fixtures; backend tests cover actual persistence and PDF data.
FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_manual_po_number_ui.py
"""
import json
import os
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
from verify_invoice_financial_year_ui import _mock_api
from verify_reagent_purchase_order_ui import party

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")


def main():
    attempts, documents, errors = [], [], []

    def fulfill(route, payload, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    def handle(route):
        path = urlparse(route.request.url).path.removeprefix("/api/v1")
        if path == "/suppliers":
            fulfill(route, [{**party, "name": "Default Supplier", "is_default": True}])
        elif path == "/purchasers":
            fulfill(route, [party])
        elif path == "/products":
            fulfill(route, [])
        elif path == "/purchase-orders" and route.request.method == "GET":
            fulfill(route, documents)
        elif path == "/purchase-orders" and route.request.method == "POST":
            payload = route.request.post_data_json
            attempts.append((route.request.headers.get("idempotency-key"), payload))
            if len(attempts) == 1:
                fulfill(route, {"detail": {"code": "duplicate_po_number", "field": "purchase_order_number", "message": "This PO No. is already in use. Enter a different number."}}, 409)
            elif len(attempts) == 2:
                fulfill(route, {"detail": "Temporary save failure; retry"}, 503)
            else:
                assert payload["purchase_order_number"] == "CLIENT/OIL-0043"
                assert payload["supplier_id"] == 1
                assert not {"purchaser", "purchaser_id", "save_purchaser_for_future"}.intersection(payload)
                order = {**payload, "id": 102, "document_type": "domestic_oils", "supplier_name": "Default Supplier", "purchaser_name": party["name"], "final_total": "118.00", "status": "draft", "version": 1, "pdf_storage_key": None}
                order.update({f"supplier_{field}": party.get(field) for field in ("gstin", "pan", "phone", "email")})
                order.update({f"supplier_{field}": value for field, value in party["address"].items() if field != "name"})
                documents.append(order)
                fulfill(route, order, 201)
        else:
            _mock_api(route)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(8000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/api/v1/**", handle)
        page.goto(f"{BASE_URL}/purchase-orders")
        page.get_by_label("PO No.", exact=True).fill("client/oil-0042")
        page.get_by_label("Material name", exact=True).fill("Domestic Oil")
        page.get_by_label("HSN/SAC", exact=True).fill("29181590")
        page.get_by_label("Quantity", exact=True).fill("1")
        page.get_by_label("Rate", exact=True).fill("100.00")
        save = page.get_by_role("button", name="Save purchase order", exact=True)
        save.click()
        expect(page.locator("#po-number-error")).to_have_text("This PO No. is already in use. Enter a different number.")
        expect(page.get_by_label("PO No.", exact=True)).to_have_value("CLIENT/OIL-0042")
        page.get_by_label("PO No.", exact=True).fill("client/oil-0043")
        save.click()
        expect(page.get_by_role("alert").filter(has_text="Temporary save failure")).to_be_visible()
        save.click()
        expect(page.get_by_role("heading", name="CLIENT/OIL-0043", exact=True)).to_be_visible()
        assert attempts[0][0] != attempts[1][0]
        assert attempts[1] == attempts[2], "Retry must retain both number and idempotency key"
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors, errors
        browser.close()
    print("Domestic PO UI: manual number, inline duplicate error, changed-intent key, retry key retention and mobile width passed.")


if __name__ == "__main__":
    main()
