"""Customer register loads later unique records without an unbounded response."""
import json
import os
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright
from verify_invoice_financial_year_ui import _mock_api


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 1000})
        requests, unexpected = [], []

        def handle(route):
            parsed = urlsplit(route.request.url)
            path = parsed.path.removeprefix("/api/v1")
            if path in ("/auth/me", "/auth/csrf", "/companies/profile"):
                _mock_api(route)
            elif path == "/customers" and route.request.method == "GET":
                query = parse_qs(parsed.query)
                offset, limit = int(query.get("offset", [0])[0]), int(query.get("limit", [100])[0])
                requests.append((offset, limit))
                rows = [{"id": index, "branch_id": 1, "name": f"Registered buyer {index}", "gstin": f"36AAAAA{index:04d}A1Z5", "pan": None, "phone": None, "email": None, "billing_address": {"address_line1": "Street", "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001"}, "shipping_address": None, "is_active": True} for index in range(offset + 1, min(offset + limit, 101) + 1)]
                route.fulfill(content_type="application/json", body=json.dumps(rows))
            else:
                unexpected.append((route.request.method, path)); route.abort()

        page.route("**/api/v1/**", handle)
        page.goto(f'{os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3000")}/customers')
        expect(page.get_by_role("table").get_by_role("row")).to_have_count(101)
        page.get_by_role("button", name="Load more customers", exact=True).click()
        expect(page.get_by_role("table").get_by_role("row")).to_have_count(102)
        expect(page.get_by_role("table")).to_contain_text("Registered buyer 101")
        expect(page.get_by_role("button", name="Load more customers", exact=True)).to_have_count(0)
        page.get_by_role("button", name="Refresh", exact=True).click()
        expect(page.get_by_role("table").get_by_role("row")).to_have_count(101)
        assert requests == [(0, 100), (100, 100), (0, 100)], requests
        assert not unexpected, unexpected
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        browser.close()
        print("Passed: bounded register paging, later customers, Refresh reset and 390px width")


if __name__ == "__main__": main()
