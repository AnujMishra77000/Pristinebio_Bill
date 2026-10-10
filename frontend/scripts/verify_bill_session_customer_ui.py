"""Four-form navigation retention and real customer edit UI; all API traffic intercepted."""
import json
import os
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright
from billing_test_pdf import blank_a4_pdf
from verify_invoice_financial_year_ui import _mock_api
from verify_saved_bill_editing_ui import CASES, fixture

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3000")
LABELS = {"sales": "Sales invoices", "reagent": "Reagent bills", "purchase": "Purchase orders", "reagent-purchase": "Reagent purchase orders"}


def navigate(page, label):
    page.get_by_role("button", name="Explore", exact=True).click()
    link = page.get_by_role("dialog", name="Explore features").get_by_role("link", name=label, exact=True)
    destination = link.get_attribute("href")
    link.click()
    expect(page).to_have_url(f"{BASE_URL}{destination}")


def main():
    failures = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for kind, collection, document_type, entry, heading in CASES:
            if os.environ.get("BILL_TEST_KIND") and os.environ["BILL_TEST_KIND"] != kind:
                continue
            page = browser.new_page(viewport={"width": 390, "height": 1000})
            page.set_default_timeout(6000)
            document = fixture(collection, document_type)
            calls, unexpected, errors = [], [], []
            state = {"customer_conflict": True, "lost_patch": True}
            page.on("pageerror", lambda error: errors.append(str(error)))
            address = {"name": "Buyer", "address_line1": "Master billing street", "address_line2": "Gate 1", "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001"}
            customer = {"id": 7, "branch_id": 1, "name": "Registered buyer", "gstin": "36ABCDE1234F1Z5", "pan": "ABCDE1234F", "email": "buyer@example.com", "phone": "9000000000", "billing_address": address, "shipping_address": {**address, "address_line1": "Separate shipping street"}, "is_active": True}
            supplier = {"id": 1, "branch_id": 1, "name": "Updated default seller", "gstin": "36ABCDE1234F1Z5", "pan": "ABCDE1234F", "phone": "9000000000", "email": "seller@example.com", "address": address, "is_active": True, "is_default": True}

            def fulfill(route, payload, status=200):
                route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

            def handle(route):
                parsed = urlsplit(route.request.url)
                path, method = parsed.path.removeprefix("/api/v1"), route.request.method
                if method == "OPTIONS": route.fulfill(status=200); return
                calls.append((method, path, parse_qs(parsed.query), route.request.post_data_json if method in ("POST", "PATCH") else None))
                if path in ("/auth/me", "/auth/csrf", "/companies/profile"): _mock_api(route)
                elif path == "/customers" and method == "GET": fulfill(route, [customer])
                elif path == "/customers/7" and method == "PATCH":
                    if state["customer_conflict"]:
                        state["customer_conflict"] = False
                        fulfill(route, {"detail": {"field": "gstin", "message": "This GSTIN already belongs to a saved customer. Edit that customer instead."}}, 409)
                    else:
                        customer.update(route.request.post_data_json)
                        fulfill(route, customer)
                elif path == "/suppliers": fulfill(route, [supplier])
                elif path == "/suppliers/1": fulfill(route, supplier)
                elif path == "/products": fulfill(route, [{"id": 8, "branch_id": 1, "name": "Updated product master", "description": "Updated description", "hsn_sac": "29181590", "unit": "kg", "base_rate": "999.00", "gst_rate": "18.00", "cess_rate": "0.00", "is_active": True}])
                elif path == "/manufacturers": fulfill(route, [{"id": 5, "branch_id": 1, "name": "Merck", "code": "MRK", "is_active": True}])
                elif path == f"/{collection}/101" and method == "GET": fulfill(route, document)
                elif path == f"/{collection}/preview": fulfill(route, {**document, "lines": document["lines"]})
                elif path == f"/{collection}/101" and method == "PATCH":
                    if state["lost_patch"]:
                        state["lost_patch"] = False
                        fulfill(route, {"detail": "Save temporarily unavailable. Your fields are retained."}, 503)
                    else:
                        body = route.request.post_data_json
                        assert body["expected_version"] == document["version"]
                        details = body.get("reagent_details", body.get("domestic_details", body))
                        document["lines"][0]["quantity"] = details["lines"][0]["quantity"]
                        document["version"] += 1
                        fulfill(route, document)
                elif path == f"/{collection}/101/preview-pdf": route.fulfill(content_type="application/pdf", body=blank_a4_pdf())
                elif path == f"/{collection}/101/submit":
                    document.update(status="pending_approval", submitted_revision=document["version"], submitted_by_id=1, version=document["version"] + 1)
                    fulfill(route, document)
                elif path == f"/{collection}/101/approve":
                    document.update(status="approved", approved_revision=document["submitted_revision"], version=document["version"] + 1)
                    fulfill(route, document)
                elif path == f"/{collection}/101/generate-pdf":
                    document.update(pdf_storage_key="isolated-final.pdf", status="pdf_generated" if collection == "invoices" else "approved")
                    fulfill(route, document)
                elif path == f"/{collection}/101/pdf": route.fulfill(content_type="application/pdf", body=blank_a4_pdf())
                else: unexpected.append((method, path)); route.abort()

            page.route("**/api/v1/**", handle)
            try:
                parameter = "invoice" if collection == "invoices" else "order"
                page.goto(f"{BASE_URL}/{entry}?{parameter}=101")
                expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
                quantity = page.get_by_label("Quantity", exact=True).first
                expect(quantity).to_have_value("1.000")
                quantity.fill("12.345")
                page.get_by_role("textbox", name="Payment terms", exact=True).fill("Retained terms after navigation")
                navigate(page, "Customers")
                expect(page.get_by_role("heading", name="Customers", exact=True)).to_be_visible()
                table = page.get_by_role("table")
                expect(table.get_by_role("row")).to_have_count(2)
                table.get_by_role("button", name="Edit", exact=True).click()
                expect(page.get_by_label("Customer name", exact=False)).to_have_value("Registered buyer")
                expect(page.get_by_label("Billing address line 1", exact=False)).to_have_value("Master billing street")
                expect(page.get_by_role("textbox", name="Shipping address line 1", exact=True)).to_have_value("Separate shipping street")
                page.get_by_label("Customer name", exact=False).fill("Corrected registered buyer")
                page.get_by_label("Billing address line 1", exact=False).fill("Corrected customer street")
                page.get_by_role("button", name="Update record", exact=True).click()
                expect(page.locator("#error-gstin")).to_contain_text("already belongs")
                expect(page.get_by_label("Customer name", exact=False)).to_have_value("Corrected registered buyer")
                page.get_by_role("button", name="Update record", exact=True).click()
                expect(table).to_contain_text("Corrected registered buyer")
                assert any(query.get("register") == ["true"] for method, path, query, _ in calls if method == "GET" and path == "/customers"), "Customer register must use the deduplicated backend view"
                assert not any(method == "POST" and path == "/customers" for method, path, _, _ in calls), "Editing must PATCH the same customer, not create another"
                navigate(page, LABELS[kind])
                expect(quantity).to_have_value("12.345")
                expect(page.get_by_role("textbox", name="Payment terms", exact=True)).to_have_value("Retained terms after navigation")
                panel = page.get_by_role("region", name="Bill submission", exact=True)
                panel.get_by_role("button", name="Preview", exact=True).click()
                expect(panel.get_by_role("alert")).to_contain_text("Save temporarily unavailable")
                navigate(page, "Customers"); navigate(page, LABELS[kind])
                expect(quantity).to_have_value("12.345")
                panel.get_by_role("button", name="Preview", exact=True).click()
                expect(panel.locator("iframe")).to_have_count(1)
                assert not any(method == "POST" and path == f"/{collection}" for method, path, _, _ in calls), "Navigation/retries must retain the existing saved ID"
                panel.get_by_role("button", name="Confirm", exact=True).click()
                expect(panel.get_by_role("button", name="Download", exact=True)).to_be_enabled()
                expect(quantity).to_be_disabled()
                navigate(page, "Customers"); navigate(page, LABELS[kind])
                expect(quantity).to_have_value("1.000")
                expect(quantity).to_be_enabled()
                expect(page.get_by_label("PO No.", exact=True) if collection == "purchase-orders" else page.get_by_label("Invoice No.", exact=True)).to_have_value("")
                if collection == "invoices":
                    # An intentional master edit must not replace already chosen
                    # transaction details until the buyer is explicitly reselected.
                    page.get_by_role("button", name="Use saved data", exact=True).click()
                    page.get_by_role("combobox", name="Saved buyer", exact=True).select_option("7")
                    page.get_by_label("Consignee name", exact=True).fill("Retained destination")
                    page.get_by_label("Invoice No.", exact=True).fill("NEW-SNAPSHOT")
                    page.get_by_role("combobox", name="Product", exact=True).select_option("8")
                    if kind == "reagent": page.get_by_role("combobox", name="MFG / Manufacturer", exact=True).select_option("5")
                    navigate(page, "Customers")
                    page.get_by_role("table").get_by_role("button", name="Edit", exact=True).click()
                    page.get_by_role("textbox", name="Billing address line 1", exact=True).fill("Later master edit")
                    page.get_by_role("button", name="Update record", exact=True).click()
                    expect(page.get_by_role("status").filter(has_text="Record updated successfully")).to_be_visible()
                    navigate(page, LABELS[kind])
                    expect(page.get_by_label("Consignee name", exact=True)).to_have_value("Retained destination")
                    page.get_by_role("textbox", name="Payment terms", exact=True).fill("Trigger retained preview")
                    page.wait_for_function("() => document.querySelector('form[data-bill-entry] input') !== null")
                    # Await the debounced request rather than sleeping or reading a
                    # previous revision's preview.
                    with page.expect_request(lambda request: request.url.endswith("/invoices/preview") and request.post_data_json.get("payment_terms") == "Retained preview checked") as preview_request:
                        page.get_by_role("textbox", name="Payment terms", exact=True).fill("Retained preview checked")
                    saved_payload = preview_request.value.post_data_json
                    assert saved_payload["buyer_customer_id"] == 7
                    assert saved_payload.get("buyer", {}).get("billing_address", {}).get("address_line1") == "Corrected customer street", saved_payload
                assert not errors, errors
                assert not unexpected, unexpected
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                print(f"Passed: {kind} retained edit, customer PATCH/error, retry, confirmation and fresh next entry")
            except Exception as failure:
                failures.append(f"{kind}: {failure}\nURL: {page.url}; page errors: {errors}; last API calls: {[(method, path) for method, path, _, _ in calls[-5:]]}")
            finally: page.close()
        browser.close()
    assert not failures, "\n".join(failures)


if __name__ == "__main__":
    main()
