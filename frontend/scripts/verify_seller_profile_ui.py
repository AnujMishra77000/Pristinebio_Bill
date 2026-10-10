"""Verify single-company billing UI does not expose branch setup.

Run with a Next.js dev server on FRONTEND_BASE_URL, for example:
FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python frontend/scripts/verify_seller_profile_ui.py
"""

from __future__ import annotations

import json
import os

from playwright.sync_api import Route, expect, sync_playwright


BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")


def _json(route: Route, payload: object, status: int = 200) -> None:
    route.fulfill(
        status=status,
        content_type="application/json",
        body=json.dumps(payload),
    )


def _mock_api(route: Route) -> None:
    url = route.request.url
    if url.endswith("/api/v1/auth/me"):
        _json(
            route,
            {
                "id": 1,
                "email": "admin@example.com",
                "full_name": "Admin User",
                "role": "admin",
                "branch_ids": [],
                "is_active": True,
                "password_change_required": False,
                "mfa_enabled": True,
                "mfa_required": True,
                "mfa_verified": True,
            },
        )
        return
    if url.endswith("/api/v1/auth/csrf"):
        _json(route, {"csrf_token": "test-csrf"})
        return
    if url.endswith("/api/v1/companies/profile"):
        _json(route, {"company": None, "seller_profile": None})
        return
    if url.endswith("/api/v1/companies"):
        _json(route, [])
        return
    if any(
        url.endswith(path)
        for path in (
            "/api/v1/branches",
            "/api/v1/customers",
            "/api/v1/products",
            "/api/v1/invoices",
            "/api/v1/suppliers",
            "/api/v1/purchase-orders",
        )
    ):
        _json(route, [])
        return
    route.continue_()


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.route("**/api/v1/**", _mock_api)

        page.goto(f"{BASE_URL}/branches")
        expect(page.get_by_role("heading", name="Seller/GST profile")).to_be_visible()
        expect(page.get_by_text("Add your company and GST details to get ready for billing.", exact=True)).to_be_visible()
        expect(page.get_by_text("Branch ID")).to_have_count(0)
        expect(page.get_by_text("Registered address is printed below your company brand on new bills.", exact=False)).to_be_visible()

        page.goto(f"{BASE_URL}/suppliers")
        expect(page.get_by_role("heading", name="Suppliers", exact=True)).to_be_visible()
        expect(page.get_by_text("Your company registered address remains separate.", exact=False)).to_be_visible()

        page.goto(f"{BASE_URL}/invoices")
        expect(page.get_by_text("Set up Seller/GST profile first").first).to_be_visible()
        expect(page.get_by_text("Internal GST branch")).to_have_count(0)

        page.goto(f"{BASE_URL}/purchase-orders")
        expect(page.get_by_text("Set up Seller/GST profile first").first).to_be_visible()
        expect(page.get_by_text("Internal GST branch")).to_have_count(0)

        browser.close()


if __name__ == "__main__":
    main()
