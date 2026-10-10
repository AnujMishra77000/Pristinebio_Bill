"""Isolated saved-buyer picker regression; intercepts every API request."""
import json
import os
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from verify_invoice_financial_year_ui import _mock_api, _json


def main():
    address = {"name": "Buyer", "address_line1": "Buyer street", "address_line2": None,
               "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001"}
    base = {"branch_id": 1, "pan": None, "email": "buyer@example.com", "phone": "9876543210",
            "billing_address": address, "shipping_address": None, "is_active": True}
    customers = [{**base, "id": 7, "name": "Apex Laboratories", "gstin": "36ABCDE1234F1Z5"},
                 {**base, "id": 8, "name": "Legacy Warehouse", "gstin": " 36abcde1234f1z5 "},
                 {**base, "id": 9, "name": "Unregistered Buyer", "gstin": None},
                 {**base, "id": 10, "name": "Disabled Buyer", "gstin": None, "is_active": False}]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        queries = []

        def mock(route):
            path = urlsplit(route.request.url).path
            if path == "/api/v1/customers":
                queries.append(urlsplit(route.request.url).query)
                _json(route, customers)
            elif path in {"/api/v1/auth/me", "/api/v1/auth/csrf", "/api/v1/companies/profile", "/api/v1/products", "/api/v1/manufacturers"}:
                _mock_api(route)
            else:
                route.fulfill(status=200, content_type="application/json", body=json.dumps([]))

        page.route("**/api/v1/**", mock)
        for path in ("invoices", "reagent-bills"):
            page.goto(f"{os.environ.get('FRONTEND_BASE_URL', 'http://127.0.0.1:3000')}/{path}")
            page.get_by_role("button", name="Use saved data", exact=True).click()
            picker = page.get_by_role("combobox", name="Saved buyer", exact=True)
            expect(picker.locator("option")).to_have_text(["Select saved buyer", "Apex Laboratories", "Unregistered Buyer"])
            search = page.get_by_role("searchbox", name="Search saved buyers by name")
            search.fill("ABCDE1234")
            expect(picker.locator("option")).to_have_text(["Select saved buyer", "Apex Laboratories"])
            search.fill("Apex")
            picker.select_option("7")
            expect(page.get_by_label("Consignee GSTIN", exact=True)).to_have_value("36ABCDE1234F1Z5")
            expect(page.get_by_label("Consignee name", exact=True)).to_be_editable()
            search.fill("unknown")
            expect(picker.locator("option")).to_have_text(["No buyer matches this search"])
            search.fill("")
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert queries and all("billing=true" in query for query in queries), queries
        browser.close()
    print("Passed: Sales/Reagent name labels, normalized GSTIN deduplication, inactive filtering, search and mobile width")


if __name__ == "__main__":
    main()
