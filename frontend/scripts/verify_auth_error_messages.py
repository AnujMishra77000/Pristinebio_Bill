"""Verify actionable login and registration network errors.

Run with a Next.js server on FRONTEND_BASE_URL, for example:
FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_auth_error_messages.py
"""

from __future__ import annotations

import os

from playwright.sync_api import Route, expect, sync_playwright


BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")


def _abort_auth_request(route: Route) -> None:
    if "/api/v1/auth/login" in route.request.url or "/api/v1/auth/register" in route.request.url:
        route.abort("failed")
        return
    route.continue_()


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.route("**/api/v1/**", _abort_auth_request)

        page.goto(f"{BASE_URL}/login")
        page.get_by_label("Email").fill("admin@example.com")
        page.get_by_label("Password", exact=True).fill("Abc123")
        page.locator('button[type="submit"]').click()
        expect(page.get_by_text("Login could not reach the billing server.")).to_be_visible()

        page.get_by_role("button", name="Register").click()
        page.get_by_label("Full name").fill("Admin User")
        page.get_by_label("Email").fill("admin@example.com")
        page.get_by_label("Password", exact=True).fill("Abc123")
        page.get_by_label("Confirm password").fill("Abc123")
        page.get_by_label("Master password").fill("MasterKey123")
        page.get_by_role("button", name="Submit registration").click()
        expect(page.get_by_text("Registration could not reach the billing server.")).to_be_visible()

        browser.close()


if __name__ == "__main__":
    main()
