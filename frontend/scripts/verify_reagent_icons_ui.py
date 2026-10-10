"""Check chemistry icons in the actual UI using isolated, read-only API fixtures."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
from verify_invoice_financial_year_ui import _mock_api

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")
SCREENSHOTS = os.environ.get("ICON_SCREENSHOT_DIR")
REAGENT_BOND = "m12 4 6.9 4v8L12 20l-6.9-4V8L12 4Z"
PURCHASE_BOND = "m8 3 5.2 3v6L8 15l-5.2-3V6L8 3Z"
KINDS = (
    ("reagent-bills", "Reagent Bill", "Reagent bills", "reagent", "Reagent bill entry", "Reagent bills", REAGENT_BOND),
    ("reagent-purchase-orders", "Reagent Purchase Order", "Reagent purchase orders", "reagent-purchase",
     "Reagent purchase order", "Reagent purchase bills", PURCHASE_BOND),
)


def check_icon(container, bond):
    icon = container.locator("svg").first
    expect(icon).to_be_visible()
    assert icon.get_attribute("aria-hidden") == "true"
    assert icon.get_attribute("stroke") == "currentColor"
    expect(icon.locator(f'path[d="{bond}"]')).to_have_count(1)
    assert icon.evaluate("""svg => [...svg.children].every(path => {
        const box = path.getBBox();
        const halfStroke = Number(svg.getAttribute('stroke-width')) / 2;
        return box.x >= halfStroke && box.y >= halfStroke &&
            box.x + box.width + halfStroke <= 24 && box.y + box.height + halfStroke <= 24;
    })"""), "Icon artwork must stay within its viewBox, including stroke"


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(5000)
        errors = []
        unmatched = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def handle(route):
            path = urlparse(route.request.url).path.removeprefix("/api/v1")
            assert route.request.method in ("GET", "OPTIONS"), "Icon verification must not save or mutate documents"
            if path == "/dashboard":
                value = {"sales_invoice_count": 0, "domestic_oils_purchase_order_count": 0,
                         "reagent_invoice_count": 0, "reagent_purchase_order_count": 0}
            elif path.endswith("/register"):
                value = {"items": [], "total": 0, "page": 1, "page_size": 10}
            elif path in ("/suppliers", "/purchasers", "/branches"):
                value = []
            elif path in ("/auth/me", "/auth/csrf", "/companies/profile", "/customers", "/products", "/invoices", "/manufacturers"):
                _mock_api(route)
                return
            else:
                unmatched.append(path)
                route.abort()
                return
            route.fulfill(status=200, content_type="application/json", body=json.dumps(value))

        page.route("**/api/v1/**", handle)
        for width in (1440, 390):
            page.set_viewport_size({"width": width, "height": 1000 if width == 1440 else 844})
            page.goto(BASE_URL)
            choices = page.get_by_role("region", name="Choose a bill type")
            registers = page.get_by_role("region", name="Saved bill registers")
            expect(choices).to_be_visible()
            for route, _, _, register, _, _, bond in KINDS:
                check_icon(choices.locator(f'a[href="/{route}"]'), bond)
                check_icon(registers.locator(f'a[href="/bill-registers/{register}"]'), bond)
            if SCREENSHOTS:
                page.screenshot(path=str(Path(SCREENSHOTS) / f"reagent-icons-{width}.png"), full_page=True)
            page.get_by_role("button", name="Explore", exact=True).click()
            dialog = page.get_by_role("dialog", name="Explore features")
            for route, _, _, _, _, _, bond in KINDS:
                check_icon(dialog.locator(f'a[href="/{route}"]'), bond)
            page.keyboard.press("Escape")
            expect(dialog).not_to_be_visible()

            page.goto(f"{BASE_URL}/billing")
            for route, _, _, _, _, _, bond in KINDS:
                check_icon(page.get_by_role("region", name="Choose a bill type").locator(f'a[href="/{route}"]'), bond)
            for route, _, _, register, entry_title, register_title, bond in KINDS:
                for path, title in ((route, entry_title), (f"bill-registers/{register}", register_title)):
                    page.goto(f"{BASE_URL}/{path}")
                    expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
                    check_icon(page.locator("#workspace-content header").first, bond)
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        assert not errors, errors
        assert not unmatched, f"Unexpected API requests were blocked: {unmatched}"
        # A real browser request must fail closed, never reach a configured API.
        page.evaluate("async () => { try { await fetch('/api/v1/icon-verification-unexpected'); } catch {} }")
        assert unmatched == ["/icon-verification-unexpected"], unmatched
        browser.close()
    print("Reagent icons: dashboard, billing shortcuts, Explore, entry/register headers, desktop/mobile and unclipped SVG bounds passed.")


if __name__ == "__main__":
    main()
