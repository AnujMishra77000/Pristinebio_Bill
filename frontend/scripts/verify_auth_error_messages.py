"""Verify actionable login/registration errors, including CSRF acquisition failure."""
from __future__ import annotations

import json
import os
from playwright.sync_api import Route, expect, sync_playwright

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")

def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        abort_csrf = False
        def mock(route: Route) -> None:
            path = route.request.url.split("/api/v1")[-1]
            if path in ("/auth/login", "/auth/register") or (path == "/auth/csrf" and abort_csrf):
                route.abort("failed")
            elif path == "/auth/csrf":
                route.fulfill(content_type="application/json", body=json.dumps({"csrf_token": "test-csrf"}))
            else:
                route.continue_()
        page.route("**/api/v1/**", mock)
        for csrf_failure in (False, True):
            abort_csrf = csrf_failure
            page.goto(f"{BASE_URL}/login")
            page.get_by_label("Email", exact=True).fill("admin@example.com")
            page.get_by_label("Password", exact=True).fill("Abc123")
            page.get_by_role("button", name="Sign in", exact=True).click()
            expect(page.locator('p[role="alert"]')).to_contain_text("Login could not reach the billing server.")
            page.get_by_role("button", name="Register as Admin", exact=True).click()
            page.get_by_label("Full name", exact=True).fill("Admin User")
            page.get_by_label("Email", exact=True).fill("admin@example.com")
            page.get_by_label("New passphrase", exact=True).fill("River!73")
            page.get_by_label("Confirm passphrase", exact=True).fill("River!73")
            page.get_by_role("button", name="Create Admin account", exact=True).click()
            expect(page.locator('p[role="alert"]')).to_contain_text("Registration could not reach the billing server.")
            expect(page.get_by_text("Failed to fetch", exact=True)).to_have_count(0)
        browser.close()
        print("PASS: actionable login/setup network errors and CSRF failures")

if __name__ == "__main__":
    main()
