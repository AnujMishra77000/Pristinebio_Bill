"""Check a production /bill build with synthetic APIs; never use client records."""
import json
import os
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    origin = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3198").rstrip("/")
    user = {"id": 1, "email": "admin@example.com", "full_name": "Test Admin", "role": "admin",
            "branch_ids": [1], "is_active": True, "password_change_required": False,
            "mfa_enabled": False, "mfa_required": False, "mfa_verified": True}
    profile = {"id": 1, "company_id": 1, "name": "Test Seller", "gstin": "36AAAAA0000A1Z5",
               "address_line1": "Test Street", "city": "Hyderabad", "state": "Telangana",
               "state_code": "36", "postal_code": "500001", "is_active": True}
    authenticated, unexpected, errors = False, [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()

        def api(route):
            nonlocal authenticated
            path = urlsplit(route.request.url).path
            if not path.startswith("/bill/api/v1/"):
                unexpected.append(path)
                route.abort()
                return
            path = path.removeprefix("/bill/api/v1")
            status, value = 200, []
            if path == "/auth/me":
                status, value = (200, user) if authenticated else (401, {"detail": "Not authenticated"})
            elif path == "/auth/csrf":
                value = {"csrf_token": "test-csrf"}
            elif path == "/auth/login":
                authenticated, value = True, {"user": user}
            elif path == "/companies/profile":
                value = {"company": {"id": 1, "legal_name": "Test Company", "is_active": True}, "seller_profile": profile}
            elif path == "/branches":
                value = [profile]
            elif path == "/auth/invitations" and route.request.method == "POST":
                value = {"id": 1, "token": "synthetic-invitation", "email": "staff@example.com", "role": "staff", "branch_ids": [1]}
            elif path.endswith("/register"):
                value = {"items": [], "total": 0, "page": 1, "page_size": 10}
            elif path == "/dashboard":
                value = {"sales_invoice_count": 0, "reagent_bill_count": 0, "credit_note_count": 0,
                         "domestic_purchase_order_count": 0, "reagent_purchase_order_count": 0}
            route.fulfill(status=status, content_type="application/json", body=json.dumps(value))

        page.route("**/api/v1/**", api)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(origin + "/bill/login")
        page.get_by_label("Email", exact=True).fill("admin@example.com")
        page.get_by_label("Password", exact=True).fill("Test12")
        page.locator("form").get_by_role("button", name="Sign in", exact=True).click()
        expect(page).to_have_url(origin + "/bill")
        for path in ("invoices", "reagent-bills", "credit-notes", "purchase-orders", "reagent-purchase-orders",
                     "bill-registers/sales", "bill-registers/reagent", "bill-registers/credit-notes",
                     "bill-registers/purchase", "bill-registers/reagent-purchase", "bank-accounts", "users"):
            response = page.goto(origin + "/bill/" + path)
            assert response.status == 200, (path, response.status)
            expect(page.locator("main")).to_be_visible()
            for href in page.locator('a[href^="/"]').evaluate_all("nodes => nodes.map(node => node.getAttribute('href'))"):
                assert href == "/bill" or href.startswith("/bill/"), href
        page.get_by_label("Invitation email", exact=True).fill("staff@example.com")
        page.get_by_role("checkbox").first.check()
        page.get_by_role("button", name="Create invitation", exact=True).click()
        expect(page.get_by_label("One-time invitation link", exact=True)).to_have_value(origin + "/bill/login#invite=synthetic-invitation")
        assert not unexpected, unexpected
        assert not errors, errors
        browser.close()
    print("Passed: /bill login redirect, 12 billing/register screens, prefixed links and API requests, invitation URL")


if __name__ == "__main__":
    main()
