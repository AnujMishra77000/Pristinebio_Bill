"""Real Sales/Reagent address-selection UI; all APIs use isolated fixtures."""
import json
import os
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from verify_invoice_financial_year_ui import _mock_api

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3000")


def main():
    billing = {"name": "Buyer Office", "address_line1": "Billing Street 1", "address_line2": "Office Block",
               "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001"}
    shipping = {"name": "Buyer Warehouse", "address_line1": "Shipping Road 2", "address_line2": "Gate 3",
                "city": "Secunderabad", "state": "Telangana", "state_code": "36", "postal_code": "500003"}
    customer = {"id": 7, "branch_id": 1, "name": "Saved Buyer", "gstin": "36ABCDE1234F1Z5", "pan": "ABCDE1234F",
                "email": "buyer@example.com", "phone": "9876543210", "billing_address": billing,
                "shipping_address": shipping, "is_active": True}
    no_shipping = {**customer, "id": 9, "name": "Billing Only Buyer", "gstin": "36FGHIJ1234K1Z5", "shipping_address": None}
    product = {"id": 8, "branch_id": 1, "name": "Saved Product", "description": "Saved product description",
               "hsn_sac": "29181590", "unit": "kg", "base_rate": "100.00", "gst_rate": "18.00", "cess_rate": "0.00", "is_active": True}
    totals = {"lines": [], "taxable_value": "100.00", "cgst_amount": "9.00", "sgst_amount": "9.00", "igst_amount": "0.00",
              "cess_amount": "0.00", "unrounded_total": "118.00", "round_off": "0.00", "final_total": "118.00", "amount_in_words": "Rupees One Hundred Eighteen Only"}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for path, kind, label in (("invoices", "sales", "Sales invoices"), ("reagent-bills", "reagent", "Reagent bills")):
            page = browser.new_page()
            attempts, unexpected, errors = [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def json_response(route, payload, status=200):
                route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

            def mock(route):
                api_path = urlsplit(route.request.url).path.removeprefix("/api/v1")
                method = route.request.method
                if api_path in ("/auth/me", "/auth/csrf", "/companies/profile"):
                    _mock_api(route)
                elif api_path == "/customers": json_response(route, [customer, no_shipping])
                elif api_path == "/products": json_response(route, [product])
                elif api_path == "/suppliers": json_response(route, [])
                elif api_path == "/manufacturers": json_response(route, [{"id": 5, "branch_id": 1, "code": "SIG", "name": "Sigma", "is_active": True}])
                elif api_path == "/invoices/preview": json_response(route, totals)
                elif api_path == "/invoices" and method == "POST":
                    attempts.append(route.request.post_data_json)
                    json_response(route, {**totals, "id": 101, "version": 1, "status": "draft", "document_type": kind,
                                          "invoice_number": f"PBPL/2026-27/{kind.upper()}-ADDR", "created_by_id": 1}, 201)
                else:
                    unexpected.append((method, api_path))
                    route.abort()

            page.route("**/api/v1/**", mock)
            page.goto(f"{BASE_URL}/{path}")
            page.get_by_role("button", name="Use saved data", exact=True).click()
            buyer = page.get_by_role("combobox", name="Saved buyer", exact=True)
            buyer.select_option("7")
            billing_choice = page.get_by_role("checkbox", name="Use billing address for shipping", exact=True)
            shipping_choice = page.get_by_role("checkbox", name="Use saved shipping address", exact=True)
            expect(shipping_choice).to_be_checked()
            expect(billing_choice).not_to_be_checked()
            # The active checkbox cannot leave shipping with no selected source.
            shipping_choice.click()
            expect(shipping_choice).to_be_checked()
            expect(billing_choice).not_to_be_checked()
            expect(page.get_by_role("textbox", name="Consignee Address line 1", exact=True)).to_have_value("Shipping Road 2")
            expect(page.get_by_label("Consignee City", exact=True)).to_have_value("Secunderabad")
            expect(page.get_by_label("Consignee Postal code", exact=True)).to_have_value("500003")
            for name, value in (("Consignee name", "Entered Warehouse"), ("Consignee PAN", "FGHIJ1234K"),
                                ("Consignee Phone", "9111111111"), ("Consignee Email", "delivery@example.com")):
                page.get_by_label(name, exact=True).fill(value)
            # Choose billing, then test single-selection keyboard behavior.
            billing_choice.check()
            expect(shipping_choice).not_to_be_checked()
            expect(page.get_by_role("textbox", name="Consignee Address line 1", exact=True)).to_have_value("Billing Street 1")
            shipping_choice.focus()
            page.keyboard.press("Space")
            expect(shipping_choice).to_be_checked()
            expect(billing_choice).not_to_be_checked()
            for name, value in (("Consignee name", "Entered Warehouse"), ("Consignee PAN", "FGHIJ1234K"),
                                ("Consignee Phone", "9111111111"), ("Consignee Email", "delivery@example.com")):
                expect(page.get_by_label(name, exact=True)).to_have_value(value)
            billing_choice.check()
            page.get_by_label("Place of supply state code", exact=True).fill("27")
            # Client-side navigation must retain choice, entered details and tax override.
            for destination in ("Customers", label):
                page.get_by_role("button", name="Explore", exact=True).click()
                page.get_by_role("dialog", name="Explore features").get_by_role("link", name=destination, exact=True).click()
                expect(page.get_by_role("heading", name="Customers" if destination == "Customers" else "Sales invoice entry" if kind == "sales" else "Reagent bill entry", exact=True)).to_be_visible()
            expect(billing_choice).to_be_checked()
            expect(page.get_by_role("textbox", name="Consignee Address line 1", exact=True)).to_have_value("Billing Street 1")
            expect(page.get_by_label("Consignee name", exact=True)).to_have_value("Entered Warehouse")
            expect(page.get_by_label("Place of supply state code", exact=True)).to_have_value("27")
            shipping_choice.check()
            expect(page.get_by_label("Place of supply state code", exact=True)).to_have_value("27")
            page.get_by_label("Invoice No.", exact=True).fill(f"{kind}-ADDR")
            page.locator("select").filter(has=page.locator('option[value="8"]')).select_option("8")
            if kind == "reagent": page.get_by_role("combobox", name="MFG / Manufacturer", exact=True).select_option("5")
            with page.expect_response(lambda response: response.request.method == "POST" and urlsplit(response.url).path == "/api/v1/invoices"):
                page.get_by_role("button", name="Save sales invoice draft" if kind == "sales" else "Save reagent bill draft", exact=True).click()
            assert len(attempts) == 1
            payload = attempts[0]
            assert payload["buyer_customer_id"] == 7
            assert payload["consignee"]["shipping_address"]["address_line1"] == "Shipping Road 2"
            assert payload["consignee"]["shipping_address"]["city"] == "Secunderabad"
            assert payload["consignee"]["name"] == "Entered Warehouse"
            assert payload["consignee"]["phone"] == "9111111111"
            assert payload["place_of_supply_state_code"] == "27"
            buyer.select_option("9")
            expect(billing_choice).to_be_checked()
            expect(shipping_choice).to_be_disabled()
            expect(page.get_by_role("textbox", name="Consignee Address line 1", exact=True)).to_have_value("Billing Street 1")
            expect(page.get_by_text("No saved shipping address for this buyer.", exact=True)).to_be_visible()
            buyer.select_option("7")
            expect(shipping_choice).to_be_checked()
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert not errors, errors
            assert not unexpected, unexpected
            page.close()
        browser.close()
    print("Passed: Sales/Reagent address defaults, exclusive choices, keyboard switching, independent contacts, retained navigation, saved payloads, absent shipping and mobile width")


if __name__ == "__main__":
    main()
