"""Entry pages must not render/fetch recent-document registers.

Run against the built frontend with isolated API fixtures:
FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_billing_entry_only_ui.py
Actual saving, permissions and financial persistence are covered by backend tests.
"""
import json
import os
import re
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
from verify_invoice_financial_year_ui import _mock_api
from verify_reagent_purchase_order_ui import party

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")
PAGES = (
    ("invoices", "Sales invoice entry", "Save sales invoice draft"),
    ("purchase-orders", "Purchase order entry", "Save purchase order"),
    ("reagent-bills", "Reagent bill entry", "Save reagent bill draft"),
    ("reagent-purchase-orders", "Reagent purchase order", "Save reagent purchase order"),
)


def main():
    failures = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for path, heading, save_label in PAGES:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(5000)
            list_requests, page_errors = [], []

            def handle(route):
                request_path = urlparse(route.request.url).path.removeprefix("/api/v1")
                if route.request.method == "GET" and request_path in ("/invoices", "/invoices/register", "/purchase-orders", "/purchase-orders/register"):
                    list_requests.append(request_path)
                    route.fulfill(status=503, content_type="application/json", body=json.dumps({"detail": "Register unavailable; entry must not depend on it"}))
                elif request_path == "/suppliers":
                    route.fulfill(status=200, content_type="application/json", body=json.dumps([{**party, "is_default": True}]))
                elif request_path == "/purchasers":
                    route.fulfill(status=200, content_type="application/json", body=json.dumps([party]))
                else:
                    _mock_api(route)

            page.route("**/api/v1/**", handle)
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            try:
                page.goto(f"{BASE_URL}/{path}")
                expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
                expect(page.get_by_role("button", name=save_label, exact=True)).to_be_visible()
                expect(page.get_by_role("button", name=save_label, exact=True)).to_be_enabled()
                expect(page.get_by_role("link", name=re.compile("Recent", re.I))).to_have_count(0, timeout=500)
                expect(page.get_by_role("button", name=re.compile("Recent", re.I))).to_have_count(0, timeout=500)
                expect(page.get_by_role("heading", name=re.compile("Recent|purchase order register", re.I))).to_have_count(0, timeout=500)
                # Reagent register loading is debounced. Use the browser's clock
                # to exercise pending timers without a slow arbitrary sleep.
                page.clock.install()
                page.clock.run_for(500)
                assert not list_requests, f"Unused register requests: {list_requests}"
                expect(page.get_by_role("alert").filter(has_text="Register unavailable")).to_have_count(0)
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                assert not page_errors, page_errors
            except Exception as error:
                failures.append(f"{path}: {error}")
            finally:
                page.close()
        browser.close()
    if failures:
        raise AssertionError("\n".join(failures))
    print("All four entry pages: no recent/register UI or list requests; creation controls and mobile width passed.")


if __name__ == "__main__":
    main()
