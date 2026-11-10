"""Real Chromium entry layout/actions; synthetic API fixtures only.

Run against the main-owned frontend with FRONTEND_BASE_URL set.
Removing wrapping or touch sizing from line actions must fail these checks.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from verify_saved_bill_editing_ui import CASES, fixture
from verify_invoice_financial_year_ui import _mock_api

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")
WIDTHS = (320, 390, 768, 1024)


def main():
    failures = []
    output = Path(os.environ.get("RESPONSIVE_OUTPUT", "/private/tmp/billing-responsive-workspace"))
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for kind, collection, document_type, entry, heading in CASES:
            page = browser.new_page(viewport={"width": 320, "height": 844})
            document = fixture(collection, document_type)
            long_name = "Synthetic long populated material and company name " * 3
            document["lines"][0]["product_name"] = long_name
            document["lines"][0]["description"] = "Long description with multiple lines\n" * 5
            document["payment_terms"] = "Synthetic payment and delivery terms " * 8
            document["supplier_name"] = long_name
            address = {"name": "Synthetic seller", "address_line1": "Synthetic street", "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001"}
            supplier = {"id": 1, "branch_id": 1, "name": "Synthetic seller", "gstin": "36ABCDE1234F1Z5", "pan": "ABCDE1234F", "phone": "9000000000", "email": "synthetic@example.com", "address": address, "is_active": True, "is_default": True}
            unexpected, errors = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def fulfill(route, payload):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

            def handle(route):
                path = urlsplit(route.request.url).path.removeprefix("/api/v1")
                if path in ("/auth/me", "/auth/csrf", "/companies/profile"):
                    _mock_api(route)
                elif path == f"/{collection}/101" and route.request.method == "GET":
                    fulfill(route, document)
                elif path.endswith("/preview"):
                    fulfill(route, document)
                elif path == "/manufacturers":
                    fulfill(route, [{"id": 5, "branch_id": 1, "name": long_name, "code": "MRK", "is_active": True}])
                elif path == "/suppliers/1":
                    fulfill(route, supplier)
                elif path == "/suppliers":
                    fulfill(route, [supplier])
                elif path in ("/customers", "/products"):
                    fulfill(route, [])
                else:
                    unexpected.append((route.request.method, path))
                    route.abort()

            page.route("**/api/v1/**", handle)
            page.goto(f"{BASE_URL}/{entry}?{'invoice' if collection == 'invoices' else 'order'}=101")
            expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
            expect(page.get_by_label("Quantity", exact=True)).to_have_value("1.000")
            add = page.get_by_role("button", name="Add line", exact=True)
            expect(add).to_be_enabled()
            for width in WIDTHS:
                page.set_viewport_size({"width": width, "height": 844})
                add.scroll_into_view_if_needed()
                # Actual hit tests exercise reachable actions, not source classes.
                add.click()
                expect(page.get_by_label("Quantity", exact=True)).to_have_count(2)
                remove = page.get_by_role("button", name="Remove", exact=True).last
                remove.scroll_into_view_if_needed()
                for label, control in (("Add line", add), ("Remove", remove)):
                    box = control.bounding_box()
                    if box["height"] < 44 or box["width"] < 44:
                        failures.append(f"{kind} {width}: {label} touch target {box['width']} x {box['height']}")
                # Inspect entry-owned form elements; shared shell checked by main.
                overflow = page.locator("form[data-bill-entry]").evaluate("""form => {
                    const bounds = form.getBoundingClientRect();
                    return [...form.querySelectorAll('input,select,textarea,button,h2,h3,a')]
                      .filter(el => el.getClientRects().length)
                      .filter(el => {const r = el.getBoundingClientRect(); return r.left < bounds.left - 1 || r.right > bounds.right + 1;})
                      .map(el => (el.getAttribute('aria-label') || el.textContent || el.tagName).slice(0,80));
                }""")
                if overflow:
                    failures.append(f"{kind} {width}: form overflow {overflow}")
                if kind == "reagent-purchase":
                    manufacturers = page.get_by_role("link", name="Manufacturers", exact=True)
                    manufacturers.scroll_into_view_if_needed()
                    manufacturers.click(trial=True)
                remove.click()
                expect(page.get_by_label("Quantity", exact=True)).to_have_count(1)
                expect(page.get_by_label("Quantity", exact=True)).to_have_value("1.000")
                expect(page.get_by_label("Rate", exact=True)).to_have_value("100.0000")
                if width in (390, 768):
                    page.get_by_label("Quantity", exact=True).scroll_into_view_if_needed()
                    page.screenshot(path=str(output / f"{kind}-entry-{width}.png"))
            assert not unexpected, unexpected
            assert not errors, errors
            page.close()
        browser.close()
    assert not failures, "\n".join(failures)
    print("Passed: four populated saved-entry forms at 320/390/768/1024; add/remove hit tests, 44px targets, form bounds and retained values; all APIs intercepted")


if __name__ == "__main__":
    main()
