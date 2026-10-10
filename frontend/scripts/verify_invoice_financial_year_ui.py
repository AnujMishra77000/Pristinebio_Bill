"""Verify Sales and Reagent forms offer manual numbering with an India-local FY prefix.

Run with a Next.js server on FRONTEND_BASE_URL, for example:
FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_invoice_financial_year_ui.py
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os

from playwright.sync_api import Route, expect, sync_playwright


BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")


def _json(route: Route, payload: object) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


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
                "mfa_enabled": False,
                "mfa_required": False,
                "mfa_verified": True,
            },
        )
    elif url.endswith("/api/v1/auth/csrf"):
        _json(route, {"csrf_token": "test-csrf"})
    elif url.endswith("/api/v1/companies/profile"):
        _json(
            route,
            {
                "company": {
                    "id": 1,
                    "legal_name": "Pristine Biopharma",
                    "trade_name": None,
                    "pan": None,
                    "registered_address": None,
                    "logo_data_uri": None,
                    "is_active": True,
                },
                "seller_profile": {
                    "id": 1,
                    "company_id": 1,
                    "name": "Pristine Biopharma",
                    "gstin": "36AAAAA0000A1Z5",
                    "address_line1": "Seller Street",
                    "address_line2": None,
                    "city": "Hyderabad",
                    "state": "Telangana",
                    "state_code": "36",
                    "postal_code": "500001",
                    "is_active": True,
                },
            },
        )
    elif any(path in url for path in ("/api/v1/customers", "/api/v1/products", "/api/v1/invoices", "/api/v1/manufacturers")):
        _json(route, [])
    else:
        route.continue_()


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(timezone_id="UTC")
        page = context.new_page()
        page.clock.install(time=datetime(2027, 3, 31, 19, 0, tzinfo=timezone.utc))
        page.route("**/api/v1/**", _mock_api)
        for path in ("invoices", "reagent-bills"):
            page.goto(f"{BASE_URL}/{path}")
            invoice_date = page.get_by_label("Invoice date", exact=True)
            invoice_number = page.get_by_label("Invoice No.", exact=True)
            prefix = page.get_by_test_id("invoice-number-prefix")
            expect(invoice_date).to_have_value("2027-04-01")
            expect(invoice_number).to_be_editable()
            expect(invoice_number).to_have_value("")
            expect(prefix).to_have_text("PBPL/2027-28/")
            invoice_number.fill("staff-007")
            expect(invoice_number).to_have_value("STAFF-007")
            invoice_date.fill("2027-03-31")
            expect(prefix).to_have_text("PBPL/2026-27/")
            expect(invoice_number).to_have_value("STAFF-007")
        browser.close()


if __name__ == "__main__":
    main()
