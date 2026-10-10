"""Verify optional second-email editing and field errors with isolated API data."""
import json
import os

from playwright.sync_api import expect, sync_playwright


def main():
    profile = {
        "company": {"id": 1, "legal_name": "Example Chemicals", "trade_name": None, "pan": None, "registered_address": "Registered Office", "logo_data_uri": None, "is_active": True},
        "seller_profile": {"id": 1, "company_id": 1, "name": "Primary GSTIN", "gstin": "36ABCDE1234F1Z5", "address_line1": "Billing Street", "address_line2": None, "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001", "phone": None, "email": "billing@example.com", "secondary_email": "orders@example.com", "bank_name": None, "bank_branch_name": None, "bank_account_name": None, "bank_account_number": None, "bank_ifsc_code": None, "terms_body": None, "is_active": True},
    }
    saved = []
    reject = False

    def api(route):
        nonlocal reject
        path = route.request.url.split("/api/v1", 1)[-1]
        status = 200
        if path == "/auth/me":
            response = {"id": 1, "email": "admin@example.com", "full_name": "Admin", "role": "admin", "branch_ids": [], "is_active": True, "password_change_required": False, "mfa_enabled": False, "mfa_required": False, "mfa_verified": True}
        elif path == "/auth/csrf":
            response = {"csrf_token": "fixture-csrf"}
        elif path == "/companies/profile":
            if route.request.method == "PUT":
                payload = route.request.post_data_json
                if reject:
                    reject = False
                    status = 422
                    response = {"detail": [{"loc": ["body", "secondary_email"], "msg": "Second email could not be accepted", "type": "value_error"}]}
                else:
                    saved.append(payload)
                    profile["seller_profile"]["secondary_email"] = payload["secondary_email"]
                    response = profile
            else:
                response = profile
        else:
            route.abort()
            raise AssertionError(f"Unexpected API request: {path}")
        route.fulfill(status=status, content_type="application/json", body=json.dumps(response))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.route("**/api/v1/**", api)
            page.goto(f'{os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")}/branches')
            secondary = page.get_by_label("Second email", exact=True)
            expect(secondary).to_have_value("orders@example.com")
            secondary.fill("dispatch@example.com")
            page.get_by_role("button", name="Update Seller/GST profile", exact=True).click()
            expect(page.get_by_text("Seller/GST profile saved. Billing will use it automatically.", exact=True)).to_be_visible()
            assert saved[-1]["email"] == "billing@example.com"
            assert saved[-1]["secondary_email"] == "dispatch@example.com"
            page.reload()
            expect(secondary).to_have_value("dispatch@example.com")
            reject = True
            secondary.fill("rejected@example.com")
            page.get_by_role("button", name="Update Seller/GST profile", exact=True).click()
            expect(page.locator("#profile-error-secondary_email")).to_have_text("Second email could not be accepted")
            expect(secondary).to_have_value("rejected@example.com")
            secondary.fill("")
            page.get_by_role("button", name="Update Seller/GST profile", exact=True).click()
            expect(page.get_by_text("Seller/GST profile saved. Billing will use it automatically.", exact=True)).to_be_visible()
            assert saved[-1]["secondary_email"] is None
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            print("Seller second-email UI: passed (save, reload, clear, field error, 390px)")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
