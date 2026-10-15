"""Intercepted correction contract across all four forms; no live backend data."""
from copy import deepcopy
import json
import os
from urllib.parse import urlsplit, parse_qs

from playwright.sync_api import expect, sync_playwright
from verify_saved_bill_editing_ui import BASE_URL, CASES, fixture
from verify_invoice_financial_year_ui import _mock_api
from billing_test_pdf import blank_a4_pdf


def verify(browser, case, scenario):
    kind, collection, document_type, entry, _ = case
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    document = fixture(collection, document_type)
    document.update(created_by_id=2, correction={"base_version": 5, "reason": "", "status": "draft", "previous_final_total": "118.00"})
    if scenario in ("pending", "pending_return"):
        document.update(status="pending_approval", submitted_revision=5, submitted_by_id=2)
        document["correction"].update(reason="Existing staged correction", status="pending_approval")
    original = deepcopy(document)
    original.update(correction=None, status="pdf_generated" if collection == "invoices" else "approved", pdf_storage_key="original.pdf")
    state = {"stale": scenario in ("stale_restart", "stale_staff"), "restarts": [], "load_error": scenario == "load_error", "conflict": scenario == "conflict", "patches": [], "requests": [], "edit_gets": 0}
    address = {"name": "Current seller", "address_line1": "Master street", "address_line2": None, "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001"}
    supplier = {"id": 1, "branch_id": 1, "name": "Current seller", "gstin": "36ABCDE1234F1Z5", "pan": None, "phone": None, "email": None, "address": address, "is_active": True, "is_default": True}
    base = f"/{collection}/101"

    def fulfill(route, payload, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    def handle(route):
        parsed = urlsplit(route.request.url)
        path, method = parsed.path.removeprefix("/api/v1"), route.request.method
        if path == "/auth/me" and scenario in ("staff", "stale_staff"):
            fulfill(route, {"id": 1, "email": "staff@example.com", "full_name": "Staff", "role": "staff", "branch_ids": [1], "is_active": True, "password_change_required": False, "mfa_enabled": False, "mfa_required": False, "mfa_verified": True})
        elif path in ("/auth/me", "/auth/csrf", "/companies/profile"): _mock_api(route)
        elif path == "/suppliers": fulfill(route, [supplier])
        elif path == "/suppliers/1": fulfill(route, supplier)
        elif path in ("/customers", "/products"): fulfill(route, [])
        elif path == "/manufacturers": fulfill(route, [{"id": 5, "branch_id": 1, "name": "Merck", "code": "MRK", "is_active": True}])
        elif path == f"/{collection}/register": fulfill(route, {"items": [original], "total": 1, "page": 1, "page_size": 10})
        elif path == base + "/correction" and method == "GET":
            if parse_qs(parsed.query).get("edit") == ["1"]: state["edit_gets"] += 1
            else: state["requests"].append((method, path))
            if state["stale"]: fulfill(route, {"detail": {"code": "version_conflict", "correction_base_changed": True, "current_version": 8, "correction_version": 6, "message": "Parent version changed. Ask Manager/Admin to restart this correction."}}, 409)
            elif state["load_error"]: fulfill(route, {"detail": "Paid or integrated bills cannot be corrected"}, 409)
            else: fulfill(route, document)
        elif path == base + "/correction/restart":
            body = route.request.post_data_json
            assert body == {"expected_version": 8, "correction_version": 6, "reason": "Restart after baseline update"}, body
            assert scenario != "stale_staff"
            state["restarts"].append(body); state["stale"] = False
            document.update(version=8, status="draft", correction={"base_version": 8, "reason": body["reason"], "status": "draft", "previous_final_total": "118.00"})
            fulfill(route, document)
        elif path == base + "/correction/return":
            assert scenario == "pending_return"
            assert route.request.post_data_json == {"expected_version": 5, "reason": "Please verify quantity"}
            document.update(status="draft", version=6, submitted_revision=None, submitted_by_id=None)
            document["correction"]["status"] = "draft"
            fulfill(route, document)
        elif path == base + "/correction" and method == "PATCH":
            body = route.request.post_data_json
            state["patches"].append(body)
            assert body["expected_version"] == document["version"], body
            assert body["correction_reason"] == "Correct reviewed quantity", body
            if state["conflict"]:
                state["conflict"] = False; document["version"] = 6; document["lines"][0]["quantity"] = "3.000"
                document["correction"]["reason"] = "Other user's saved reason"
                fulfill(route, {"detail": {"code": "version_conflict", "message": "Another user changed this correction"}}, 409)
            else:
                document["version"] += 1
                details = body.get("domestic_details") or body.get("reagent_details") or body
                document["lines"][0]["quantity"] = details["lines"][0]["quantity"]
                document["correction"]["reason"] = body["correction_reason"]
                document["final_total"] = "236.00"
                fulfill(route, document)
        elif path.endswith("/preview"): fulfill(route, {**document, "lines": []})
        elif path == base + "/correction/preview-pdf":
            state["requests"].append((method, path))
            assert route.request.post_data_json["expected_version"] == document["version"]
            route.fulfill(status=200, content_type="application/pdf", body=blank_a4_pdf())
        elif path == base + "/correction/submit":
            state["requests"].append((method, path))
            assert route.request.post_data_json["expected_version"] == document["version"]
            document.update(status="pending_approval", submitted_revision=document["version"], submitted_by_id=1)
            document["correction"]["status"] = "pending_approval"
            fulfill(route, document)
        elif path == base + "/correction/approve":
            state["requests"].append((method, path))
            assert scenario != "staff"
            assert route.request.post_data_json["expected_version"] == document["version"]
            document.update(status="approved", approved_revision=document["version"], version=document["version"] + 1, correction=None)
            fulfill(route, document)
        elif path == base + "/generate-pdf":
            state["requests"].append((method, path))
            assert document["correction"] is None
            document.update(pdf_storage_key="corrected.pdf", status="pdf_generated" if collection == "invoices" else "approved")
            fulfill(route, document)
        elif path == base + "/pdf":
            state["requests"].append((method, path))
            route.fulfill(status=200, content_type="application/pdf", body=blank_a4_pdf())
        else: raise AssertionError(f"Unexpected request: {method} {path}")

    page.route("**/api/v1/**", handle)
    parameter = "invoice" if collection == "invoices" else "order"
    page.goto(f"{BASE_URL}/{entry}?{parameter}=101&correction=1")
    quantity = page.get_by_label("Quantity", exact=True)
    panel = page.get_by_role("region", name="Bill submission", exact=True)
    if scenario in ("stale_restart", "stale_staff"):
        expect(page.get_by_role("alert").filter(has_text="Ask Manager/Admin to restart")).to_be_visible()
        expect(quantity).to_be_disabled()
        restart_button = page.get_by_role("button", name="Restart correction", exact=True)
        if scenario == "stale_staff":
            expect(restart_button).to_have_count(0)
            expect(page.get_by_text("Contact Manager/Admin to restart this correction from the latest confirmed bill.", exact=True)).to_be_visible()
        else:
            expect(restart_button).to_be_disabled()
            page.get_by_label("Restart reason", exact=True).fill("Restart after baseline update")
            page.once("dialog", lambda dialog: dialog.dismiss()); restart_button.click()
            assert not state["restarts"]
            expect(quantity).to_be_disabled()
            page.once("dialog", lambda dialog: dialog.accept()); restart_button.click()
            expect(quantity).to_be_enabled()
            expect(panel.get_by_label("Correction reason", exact=True)).to_have_value("Restart after baseline update")
            assert len(state["restarts"]) == 1
        assert not errors, errors
        print(f"Passed: {kind} {scenario}", flush=True)
        page.close(); return
    if scenario == "load_error":
        expect(page.get_by_role("alert").filter(has_text="Paid or integrated bills cannot be corrected")).to_be_visible()
        expect(quantity).to_be_disabled()
        assert not state["patches"]
        state["load_error"] = False
        page.get_by_role("button", name="Retry loading bill", exact=True).click()
    expect(quantity).to_have_value("1.000")
    number = page.get_by_label("Invoice No." if collection == "invoices" else "PO No.", exact=True)
    expect(number).to_have_attribute("readonly", "")
    reason = panel.get_by_label("Correction reason", exact=True)
    expect(reason).to_be_visible()
    expect(panel).to_contain_text("original confirmed bill")
    if scenario == "pending_return":
        expect(quantity).to_be_disabled()
        return_button = panel.get_by_role("button", name="Return for correction", exact=True)
        expect(return_button).to_be_disabled()
        panel.get_by_label("Reviewer reason", exact=True).fill("Please verify quantity")
        return_button.click()
        expect(quantity).to_be_enabled()
        expect(reason).to_have_value("Existing staged correction")
        expect(return_button).to_have_count(0)
        assert state["edit_gets"] >= 2, "Returned draft must rehydrate through the saved loader"
        assert not errors, errors
        print(f"Passed: {kind} {scenario}", flush=True)
        page.close(); return
    if scenario == "pending":
        expect(quantity).to_be_disabled(); expect(reason).to_be_disabled()
        expect(panel.get_by_role("button", name="Confirm", exact=True)).to_be_disabled()
    else:
        panel.get_by_role("button", name="Preview", exact=True).click()
        expect(panel.get_by_role("alert")).to_contain_text("correction reason")
        assert not state["patches"]
        reason.fill("Correct reviewed quantity")
        if scenario == "admin":
            page.get_by_role("button", name="Explore", exact=True).click()
            page.get_by_role("link", name="Billing", exact=True).click()
            page.wait_for_url("**/billing")
            page.go_back()
            expect(reason).to_have_value("Correct reviewed quantity")
            page.locator('form[data-bill-entry] button[type="submit"]').click()
            expect(panel.get_by_role("status")).to_contain_text("Draft saved")
            page.reload()
            expect(reason).to_have_value("Correct reviewed quantity")
        quantity.fill("2.000")
    panel.get_by_role("button", name="Preview", exact=True).click()
    if scenario == "conflict":
        expect(panel.get_by_role("alert")).to_contain_text("Another user")
        expect(quantity).to_have_value("2.000"); expect(reason).to_have_value("Correct reviewed quantity")
        reload_button = page.get_by_role("button", name="Reload latest revision", exact=True)
        page.once("dialog", lambda dialog: dialog.dismiss()); reload_button.click()
        expect(quantity).to_have_value("2.000")
        page.once("dialog", lambda dialog: dialog.accept()); reload_button.click()
        expect(quantity).to_have_value("3.000"); expect(reason).to_have_value("Other user's saved reason")
        reason.fill("Correct reviewed quantity")
        quantity.fill("4.000"); panel.get_by_role("button", name="Preview", exact=True).click()
    expect(panel.locator("iframe")).to_have_count(1)
    panel.get_by_role("button", name="Confirm", exact=True).click()
    if scenario == "staff":
        expect(panel).to_contain_text("Submitted for approval")
        expect(panel.get_by_role("button", name="Download", exact=True)).to_be_disabled()
        assert ("POST", base + "/correction/approve") not in state["requests"]
    else:
        expect(panel.get_by_role("button", name="Download", exact=True)).to_be_enabled()
        assert state["requests"][-2:] == [("POST", base + "/generate-pdf"), ("GET", base + "/pdf")]
    assert state["edit_gets"] >= 1
    assert not errors, errors
    print(f"Passed: {kind} {scenario}", flush=True)
    page.close()


def verify_queue(browser):
    page = browser.new_page()
    state = {"fail": True, "gets": 0}
    items = [{"collection": collection, "document_id": 101 + index, "document_type": document_type, "document_number": kind.upper(), "version": 6,
              "reason": "Reviewed quantity correction", "previous_final_total": "118.00", "final_total": "236.00", "created_by_id": 2, "submitted_by_id": 2}
             for index, (kind, collection, document_type, _, _) in enumerate(CASES)]

    def handle(route):
        path = urlsplit(route.request.url).path.removeprefix("/api/v1")
        if path in ("/auth/me", "/auth/csrf", "/companies/profile"): _mock_api(route)
        elif path in ("/invoices/approval-queue", "/purchase-orders/approval-queue"): route.fulfill(content_type="application/json", body="[]")
        elif path == "/bill-corrections/pending":
            state["gets"] += 1
            route.fulfill(status=503 if state["fail"] else 200, content_type="application/json", body=json.dumps({"detail": "Correction queue temporarily unavailable"} if state["fail"] else {"items": items, "total": 4, "page": 1, "page_size": 50}))
        else: raise AssertionError(f"Unexpected queue request: {path}")

    page.route("**/api/v1/**", handle)
    page.goto(f"{BASE_URL}/approvals")
    expect(page.get_by_role("alert").filter(has_text="Correction queue temporarily unavailable")).to_be_visible()
    state["fail"] = False
    page.get_by_role("button", name="Refresh corrections", exact=True).click()
    queue = page.get_by_role("region", name="Confirmed bill corrections", exact=True)
    expect(queue.get_by_role("link", name="Review correction", exact=True)).to_have_count(4)
    expect(queue.get_by_text("Reviewed quantity correction", exact=True)).to_have_count(4)
    expect(queue.get_by_text("Previous confirmed: ₹118.00 · Correction: ₹236.00", exact=True)).to_have_count(4)
    expect(queue.get_by_role("button", name="Approve", exact=True)).to_have_count(0)
    for index, (_, collection, _, entry, _) in enumerate(CASES):
        expect(queue.get_by_role("link", name="Review correction", exact=True).nth(index)).to_have_attribute("href", f"/{entry}?{'invoice' if collection == 'invoices' else 'order'}={101 + index}&correction=1")
    assert state["gets"] == 2
    page.close()


def main():
    scenarios = os.environ.get("CORRECTION_UI_SCENARIOS", "admin,staff,conflict,pending,load_error,pending_return,stale_restart,stale_staff").split(",")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for case in CASES:
            for scenario in scenarios:
                verify(browser, case, scenario)
        verify_queue(browser)
        browser.close()
    print(f"Passed: {len(CASES) * len(scenarios)} intercepted correction flows across four forms plus approval queue: {', '.join(scenarios)}")


if __name__ == "__main__": main()
