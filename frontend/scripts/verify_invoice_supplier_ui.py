"""Sales/Reagent supplier selection and supplier-management browser regressions.

Uses isolated API fixtures; real persistence/permissions are covered by backend tests.
FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_invoice_supplier_ui.py
"""
import json
import os
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright
from verify_invoice_financial_year_ui import _mock_api
from verify_reagent_purchase_order_ui import party, totals
from billing_test_pdf import blank_a4_pdf

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        for entry in ("invoices", "reagent-bills"):
            suppliers = [
                {**party, "id": 1, "name": "Alpha Supplier", "is_default": True,
                 "address": {**party["address"], "address_line1": "Alpha Warehouse"}},
                {**party, "id": 2, "name": "Beta Supplier", "is_default": False,
                 "address": {**party["address"], "address_line1": "Beta Warehouse"}},
            ]
            attempts, searches, errors, patches = [], [], [], []
            documents = {}
            reject_supplier_edit = [True]
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(8000)
            page.on("pageerror", lambda error: errors.append(str(error)))

            def fulfill(route, body, status=200):
                route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

            def handle(route):
                url = urlparse(route.request.url)
                path = url.path.removeprefix("/api/v1")
                method = route.request.method
                if path == "/suppliers":
                    query = parse_qs(url.query)
                    assert query.get("branch_id") == ["1"]
                    assert query.get("active_only") == ["true"]
                    search = query.get("search", [""])[0]
                    searches.append(search)
                    if search == "offline": fulfill(route, {"detail": "Supplier search unavailable; retry"}, 503)
                    else: fulfill(route, [s for s in suppliers if search.lower() in s["name"].lower()])
                elif path == "/manufacturers":
                    fulfill(route, [{"id": 5, "branch_id": 1, "code": "SIG", "name": "Sigma", "is_active": True}])
                elif path == "/invoices/preview":
                    fulfill(route, {**totals, "lines": [{**route.request.post_data_json["lines"][0], **totals, "line_total": "189.00"}]})
                elif path == "/invoices" and method == "POST":
                    payload = route.request.post_data_json
                    attempts.append((route.request.headers.get("idempotency-key"), payload))
                    documents.setdefault(101, {**payload, **totals, "id": 101, "version": 1, "status": "draft", "pdf_storage_key": None})
                    if len(attempts) == 1: fulfill(route, {"detail": "Temporary save failure; retry"}, 503)
                    else: fulfill(route, documents[101], 200)
                elif path == "/invoices/101" and method == "PATCH":
                    payload = route.request.post_data_json
                    assert payload["expected_version"] == documents[101]["version"]
                    if reject_supplier_edit[0]:
                        reject_supplier_edit[0] = False
                        fulfill(route, {"detail": {"field": "supplier_id", "message": "Supplier is inactive; choose another active supplier"}}, 422)
                        return
                    patches.append(payload)
                    documents[101].update(payload, version=documents[101]["version"] + 1)
                    fulfill(route, documents[101])
                elif path == "/invoices/101/preview-pdf":
                    route.fulfill(status=200, content_type="application/pdf", body=blank_a4_pdf())
                else: _mock_api(route)

            page.route("**/api/v1/**", handle)
            page.goto(f"{BASE_URL}/{entry}")
            picker = page.get_by_role("region", name="Supplier selection", exact=True)
            expect(picker).to_be_visible()
            supplier = picker.get_by_label("Supplier", exact=True)
            expect(supplier).to_have_value("1")
            search = picker.get_by_label("Search suppliers by name", exact=True)
            search.fill("Beta")
            with page.expect_response(lambda response: parse_qs(urlparse(response.url).query).get("search") == ["Beta"]):
                picker.get_by_role("button", name="Search suppliers", exact=True).click()
            expect(supplier.locator("option[value='2']")).to_have_count(1)
            supplier.select_option("2")
            expect(picker).to_contain_text("Beta Warehouse")
            picker.get_by_role("button", name="Refresh suppliers", exact=True).click()
            expect(supplier).to_have_value("2")
            search.fill("offline")
            search.press("Enter")
            expect(picker.get_by_role("alert")).to_contain_text("Supplier search unavailable")
            expect(supplier).to_have_value("2")
            search.fill("Alpha")
            with page.expect_response(lambda response: parse_qs(urlparse(response.url).query).get("search") == ["Alpha"]):
                picker.get_by_role("button", name="Search suppliers", exact=True).click()
            expect(supplier.locator("option[value='1']")).to_have_count(1)
            expect(supplier).to_have_value("2")  # searching never loses the pinned selection
            page.get_by_label("Invoice No.", exact=True).fill("SUPPLIER-001")
            page.get_by_label("Buyer/vendor name", exact=True).fill("Manual Buyer")
            for label, value in (("Address line 1", "Buyer Road"), ("City", "Hyderabad"), ("State", "Telangana"), ("Postal code", "500001")):
                page.get_by_label(label, exact=True).fill(value)
            product_input = page.locator("form[data-bill-entry] label").filter(has_text="Product name").locator("textarea")
            product_input.fill("Original Product")
            page.get_by_label("HSN/SAC", exact=True).fill("29181590")
            page.get_by_label("Rate", exact=True).fill("100.0000")
            if entry == "reagent-bills":
                page.get_by_role("combobox", name="MFG / Manufacturer", exact=True).select_option("5")
                page.get_by_label("Item Description", exact=True).fill("Reagent description")
            panel = page.get_by_role("region", name="Bill submission", exact=True)
            preview = panel.get_by_role("button", name="Preview", exact=True)
            preview.click()
            expect(panel.get_by_role("alert")).to_contain_text("Temporary save failure")
            expect(supplier).to_have_value("2")
            preview.click()
            expect(panel.locator("iframe")).to_have_count(1)
            assert len(attempts) == 2 and attempts[0] == attempts[1]
            assert attempts[0][1]["supplier_id"] == 2 and attempts[0][0]
            expect(supplier).to_be_disabled()
            panel.get_by_role("button", name="Edit", exact=True).click()
            supplier.select_option("1")
            preview.click()
            expect(picker.get_by_role("alert")).to_contain_text("Supplier is inactive")
            expect(product_input).to_have_value("Original Product")
            supplier.select_option("")
            supplier.select_option("1")
            expect(picker.get_by_role("alert")).to_have_count(0)
            preview.click()
            expect(panel.locator("iframe")).to_have_count(1)
            assert len(documents) == 1 and patches[-1]["supplier_id"] == 1
            assert patches[-1]["expected_version"] == 1
            assert "Beta" in searches and "Alpha" in searches
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert not errors, errors
            page.close()

        # Empty HTTP 204 is the real supplier deletion contract, not JSON success.
        page = browser.new_page()
        page.set_default_timeout(8000)
        records = [{**party, "name": "Used Supplier", "is_default": True}]
        writes = []

        def supplier_management(route):
            path = urlparse(route.request.url).path.removeprefix("/api/v1")
            method = route.request.method
            if path == "/suppliers" and method == "GET": fulfill(route, records)
            elif path == "/suppliers" and method == "POST":
                payload = route.request.post_data_json
                writes.append(payload)
                record = {**payload, "id": 2, "branch_id": 1}
                records.append(record)
                fulfill(route, record, 201)
            elif path == "/suppliers/2" and method == "DELETE":
                records[:] = [record for record in records if record["id"] != 2]
                route.fulfill(status=204)
            elif path == "/suppliers/1" and method == "DELETE":
                fulfill(route, {"detail": "Supplier is used by an existing invoice; deactivate it instead of deleting it"}, 409)
            elif path == "/suppliers/1" and method == "PATCH":
                records[0].update(route.request.post_data_json, is_default=False)
                fulfill(route, records[0])
            else: _mock_api(route)

        page.route("**/api/v1/**", supplier_management)
        page.on("dialog", lambda dialog: dialog.accept())
        page.goto(f"{BASE_URL}/suppliers")
        for field, value in (("name", "New Supplier"), ("address_line1", "New Warehouse"), ("city", "Hyderabad"), ("state", "Telangana"), ("state_code", "36"), ("postal_code", "500001")):
            page.locator(f"#master-{field}").fill(value)
        page.get_by_label("Set as default supplier", exact=True).uncheck()
        page.get_by_role("button", name="Save record", exact=True).click()
        new_row = page.get_by_role("row").filter(has=page.get_by_role("cell", name="New Supplier", exact=True))
        expect(new_row).to_have_count(1)
        assert writes[0]["address"]["address_line1"] == "New Warehouse"
        new_row.get_by_role("button", name="Delete", exact=True).click()
        expect(page.get_by_role("status").filter(has_text="Supplier deleted permanently")).to_be_visible()
        expect(new_row).to_have_count(0)
        used_row = page.get_by_role("row").filter(has=page.get_by_role("cell", name="Used Supplier", exact=True))
        used_row.get_by_role("button", name="Delete", exact=True).click()
        expect(page.get_by_role("alert").filter(has_text="deactivate it instead")).to_be_visible()
        used_row.get_by_role("button", name="Deactivate", exact=True).click()
        expect(used_row.get_by_role("button", name="Activate", exact=True)).to_be_visible()
        assert len(records) == 1 and records[0]["is_active"] is False
        browser.close()
    print("Sales/Reagent supplier search, retries, field errors, versioned edits and mobile; Supplier create/204-delete/409-deactivate passed.")


if __name__ == "__main__":
    main()
