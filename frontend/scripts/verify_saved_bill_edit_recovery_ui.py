"""Failed opens cannot create bills; concurrent edits retain fields until reload."""
from copy import deepcopy
import json
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from verify_saved_bill_editing_ui import BASE_URL, CASES, fixture
from verify_invoice_financial_year_ui import _mock_api
from billing_test_pdf import blank_a4_pdf


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for kind, collection, document_type, entry, _ in CASES:
            for scenario in ("failed_load", "wrong_type", "invalid_id", "conflict"):
                page = browser.new_page()
                doc = fixture(collection, document_type)
                state = {"failed": scenario == "failed_load", "conflict": scenario == "conflict", "gets": 0, "creates": 0, "patches": []}
                address = {"name": "Master", "address_line1": "Master street", "address_line2": None, "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001"}
                supplier = {"id": 1, "branch_id": 1, "name": "Master", "gstin": "36ABCDE1234F1Z5", "pan": None, "phone": None, "email": None, "address": address, "is_active": True, "is_default": True}

                def fulfill(route, value, status=200):
                    route.fulfill(status=status, content_type="application/json", body=json.dumps(value))

                def mock(route):
                    path = urlsplit(route.request.url).path.removeprefix("/api/v1")
                    method = route.request.method
                    if path in ("/auth/me", "/auth/csrf", "/companies/profile"): _mock_api(route)
                    elif path == "/suppliers": fulfill(route, [supplier])
                    elif path == "/suppliers/1": fulfill(route, supplier)
                    elif path == "/customers": fulfill(route, [])
                    elif path == "/products": fulfill(route, [])
                    elif path == "/manufacturers": fulfill(route, [{"id": 5, "branch_id": 1, "code": "MRK", "name": "Merck", "is_active": True}])
                    elif path == f"/{collection}/101" and method == "GET":
                        state["gets"] += 1
                        if state["failed"]: fulfill(route, {"detail": "Saved bill loading failed"}, 503)
                        elif scenario == "wrong_type": fulfill(route, {**doc, "document_type": "reagent" if document_type != "reagent" else "sales"})
                        else: fulfill(route, doc)
                    elif path == f"/{collection}/101" and method == "PATCH":
                        body = route.request.post_data_json
                        state["patches"].append(body)
                        if state["conflict"]:
                            state["conflict"] = False; doc["version"] = 6; doc["lines"][0]["quantity"] = "3.000"
                            fulfill(route, {"detail": {"code": "version_conflict", "message": "Another user changed this bill"}}, 409)
                        else:
                            assert body["expected_version"] == 6, body
                            doc["version"] = 7; fulfill(route, doc)
                    elif path == f"/{collection}" and method == "POST": state["creates"] += 1; route.abort()
                    elif path.endswith("/preview"): fulfill(route, {**doc, "lines": []})
                    elif path.endswith("/preview-pdf"): route.fulfill(status=200, content_type="application/pdf", body=blank_a4_pdf())
                    else: route.abort()

                page.route("**/api/v1/**", mock)
                parameter = "invoice" if collection == "invoices" else "order"
                page.goto(f"{BASE_URL}/{entry}?{parameter}={'invalid' if scenario == 'invalid_id' else '101'}")
                quantity = page.get_by_label("Quantity", exact=True)
                panel = page.get_by_role("region", name="Bill submission", exact=True)
                if scenario != "conflict":
                    expect(quantity).to_be_disabled()
                    expect(panel.get_by_role("button", name="Preview", exact=True)).to_be_disabled()
                    expect(page.get_by_role("button", name="Retry loading bill", exact=True)).to_be_visible()
                    assert state["creates"] == 0 and not state["patches"]
                    if scenario == "invalid_id": assert state["gets"] == 0
                    if scenario == "failed_load":
                        state["failed"] = False
                        page.get_by_role("button", name="Retry loading bill", exact=True).click()
                        expect(quantity).to_have_value("1.000")
                        expect(quantity).to_be_enabled()
                        assert state["gets"] == 2 and state["creates"] == 0
                else:
                    expect(quantity).to_have_value("1.000")
                    quantity.fill("2.000")
                    panel.get_by_role("button", name="Preview", exact=True).click()
                    expect(panel.get_by_role("alert")).to_contain_text("Another user changed this bill")
                    expect(quantity).to_have_value("2.000")
                    reload_button = page.get_by_role("button", name="Reload latest revision", exact=True)
                    page.once("dialog", lambda dialog: dialog.dismiss())
                    reload_button.click()
                    expect(quantity).to_have_value("2.000")
                    assert state["gets"] == 1
                    page.once("dialog", lambda dialog: dialog.accept())
                    reload_button.click()
                    expect(quantity).to_have_value("3.000")
                    quantity.fill("4.000")
                    panel.get_by_role("button", name="Preview", exact=True).click()
                    expect(panel.locator("iframe")).to_have_count(1)
                    assert len(state["patches"]) == 2
                    assert state["patches"][1]["expected_version"] == 6
                    assert state["creates"] == 0
                page.close()
        browser.close()
    print("Passed: 16 scenarios across four forms — failed load/retry, wrong type, invalid ID, and conflict cancel/reload/versioned retry without duplicate creation")


if __name__ == "__main__": main()
