"""Responsive real-page checks with intercepted fixture APIs, never client data.

FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_responsive_workspace_ui.py
Optional RESPONSIVE_WIDTHS / RESPONSIVE_PATHS select a targeted subset.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from playwright.sync_api import expect, sync_playwright
from billing_test_pdf import blank_a4_pdf
from verify_saved_bill_editing_ui import fixture
from verify_invoice_financial_year_ui import _mock_api

BASE = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")
WIDTHS = [int(value) for value in os.environ.get("RESPONSIVE_WIDTHS", "320,390,768,1024,1440").split(",")]
PATHS = os.environ.get("RESPONSIVE_PATHS", "/,/billing,/bill-registers/sales,/bill-registers/reagent,/bill-registers/purchase,/bill-registers/reagent-purchase,/customers,/products,/suppliers,/purchasers,/manufacturers,/branches,/bank-accounts,/transporters,/terms,/approvals,/payments,/integrations,/users,/settings,/security,/login,/register").split(",")
OUTPUT = Path(os.environ.get("RESPONSIVE_OUTPUT", "/private/tmp/billing-responsive-workspace"))
LONG = "International Laboratory Raw Material Distribution and Research Company " * 2
ADDRESS = {"name": LONG, "address_line1": "Industrial Estate, Laboratory Building, Research Campus " * 3, "address_line2": "Gate 2", "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001"}
PARTY = {"id": 1, "branch_id": 1, "name": LONG, "gstin": "36ABCDE1234F1Z5", "pan": "ABCDE1234F", "phone": "9000000000", "email": "laboratory-research-and-distribution@example.com", "address": ADDRESS, "billing_address": ADDRESS, "shipping_address": ADDRESS, "is_active": True, "is_default": True}
USER = {"id": 1, "email": "admin@example.com", "full_name": LONG, "role": "admin", "branch_ids": [1], "is_active": True, "password_change_required": False, "mfa_enabled": False, "mfa_required": False, "mfa_verified": True}


def install_api(page):
    unexpected = []

    def handle(route):
        parsed = urlsplit(route.request.url)
        path = parsed.path.removeprefix("/api/v1")
        query = parse_qs(parsed.query)
        def send(value):
            route.fulfill(status=200, content_type="application/json", body=json.dumps(value))
        if path == "/auth/logout": route.fulfill(status=503, content_type="application/json", body='{"detail":"Unable to log out right now. Your billing work is retained; please retry."}')
        elif path == "/auth/me": send(USER)
        elif path in ("/auth/csrf", "/companies/profile"): _mock_api(route)
        elif path in ("/customers", "/suppliers", "/purchasers"): send([PARTY])
        elif path == "/products": send([{**PARTY, "hsn_sac": "29181590", "description": LONG, "unit": "kg", "base_rate": "100.0000", "gst_rate": "18.00", "cess_rate": "0.00"}])
        elif path == "/manufacturers": send([{**PARTY, "code": "MRK"}])
        elif path == "/branches": send([{**PARTY, **ADDRESS, "company_id": 1}])
        elif path == "/bank-accounts": send([{**PARTY, "bank_name": LONG, "account_holder_name": LONG, "account_number": "1234567890123456", "ifsc_code": "ABCD0123456", "branch_name": LONG}])
        elif path == "/transporters": send([{**PARTY, "transporter_id": "TRANS-123", "contact_person": LONG}])
        elif path in ("/terms", "/terms-and-conditions"): send([{**PARTY, "title": LONG, "content": LONG, "text": LONG}])
        elif path == "/users": send([USER])
        elif path in ("/auth/invitations", "/auth/audit", "/auth/sessions"): send([])
        elif path == "/dashboard": send({"sales_invoice_count": 12, "reagent_invoice_count": 5, "domestic_oils_purchase_order_count": 8, "reagent_purchase_order_count": 3})
        elif path == "/integrations/providers": send([{"provider_key": "client-accounting", "environment": "unconfigured", "available": False, "reason": LONG}])
        elif path in ("/integrations/jobs", "/integrations/reconciliation"): send({"items": [], "total": 0})
        elif path == "/payments/receipts": send({"items": [{"id": 1, "receipt_number": "RCPT-2026-00001", "receipt_date": "2026-10-15", "amount": "118.00", "allocated_amount": "0.00", "unallocated_amount": "118.00", "status": "posted"}], "total": 1})
        elif path == "/bill-corrections/pending": send({"items": [], "total": 0, "page": 1, "page_size": 50})
        elif path.endswith("/approval-queue"):
            send([fixture("purchase-orders" if path.startswith("/purchase-orders") else "invoices", "domestic_oils" if path.startswith("/purchase-orders") else "sales")])
        elif path.endswith("/register"):
            collection = path.split("/")[1]
            value = fixture(collection, query.get("document_type", ["sales" if collection == "invoices" else "domestic_oils"])[0])
            value.update(buyer_name=LONG, supplier_name=LONG)
            send({"items": [value], "total": 1, "page": 1, "page_size": 10})
        elif path in ("/invoices/101", "/purchase-orders/101"):
            collection = path.split("/")[1]
            value = fixture(collection, "sales" if collection == "invoices" else "domestic_oils")
            value.update(buyer_name=LONG, supplier_name=LONG)
            send(value)
        elif path.endswith("/preview-pdf"):
            route.fulfill(status=200, content_type="application/pdf", body=blank_a4_pdf())
        else:
            unexpected.append((route.request.method, path))
            route.fulfill(status=500, content_type="application/json", body='{"detail":"Unexpected responsive test request"}')
    page.route("**/api/v1/**", handle)
    return unexpected


def layout_issues(page, phone):
    return page.evaluate("""phone => {
      const issues = [];
      if (document.documentElement.scrollWidth > innerWidth + 1) issues.push(`page overflow ${document.documentElement.scrollWidth}/${innerWidth}`);
      const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
      const horizontal = el => { for (let p = el.parentElement; p; p = p.parentElement) if (['auto','scroll'].includes(getComputedStyle(p).overflowX) && p.scrollWidth > p.clientWidth) return true; return false; };
      for (const el of document.querySelectorAll('input:not([type=checkbox]):not([type=radio]),textarea,select,button,.ui-button,.ui-button-primary')) {
        if (!visible(el) || el.closest('nextjs-portal')) continue;
        const box = el.getBoundingClientRect();
        const name = (el.getAttribute('aria-label') || el.textContent || el.getAttribute('name') || el.tagName).trim().slice(0,65);
        if (!horizontal(el) && (box.left < -1 || box.right > innerWidth + 1)) issues.push(`control outside viewport: ${name}`);
        if (phone && !el.disabled && el.matches('button,.ui-button,.ui-button-primary') && box.height < 43.5) issues.push(`small touch target: ${name} ${box.height}`);
        if (phone && el.matches('input:not([type=checkbox]):not([type=radio]),textarea,select') && parseFloat(getComputedStyle(el).fontSize) < 16) issues.push(`small entry text: ${name}`);
      }
      return [...new Set(issues)];
    }""", phone)


def main():
    failures = []
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in WIDTHS:
            for path in PATHS:
                page = browser.new_page(viewport={"width": width, "height": 900 if width < 768 else 1024}, is_mobile=width < 768, has_touch=width < 1100)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                unexpected = install_api(page)
                page.goto(BASE + path)
                expect(page.get_by_role("heading", level=1).first).to_be_visible()
                # Wait for asynchronous record loading, not a fixed sleep.
                if path == "/customers": expect(page.get_by_role("cell", name=LONG, exact=True).first).to_be_visible()
                if path.startswith("/bill-registers/"): expect(page.get_by_role("button", name="View bill", exact=False).first).to_be_visible()
                found = layout_issues(page, width < 640)
                if path == "/" and width in (320, 768, 1440):
                    page.screenshot(path=str(OUTPUT / f"dashboard-{width}.png"), full_page=True)
                if path in ("/login", "/register") and width == 320: page.screenshot(path=str(OUTPUT / f"{path[1:]}-320.png"), full_page=True)
                if path == "/" and width == 320:
                    page.get_by_role("button", name="Explore", exact=True).click()
                    dialog = page.get_by_role("dialog", name="Explore features")
                    expect(dialog).to_be_visible()
                    page.set_viewport_size({"width": 667, "height": 375})
                    close = dialog.get_by_role("button", name="Close Explore")
                    close.scroll_into_view_if_needed()
                    box = close.bounding_box()
                    assert box and box["y"] >= 0 and box["y"] + box["height"] <= 375, "Explore close unreachable in landscape"
                    close.click()
                    expect(dialog).not_to_be_visible()
                    page.set_viewport_size({"width": width, "height": 900})
                    page.get_by_role("button", name="Log out", exact=True).click()
                    alert = page.get_by_role("alert").filter(has_text="Unable to log out right now")
                    expect(alert).to_be_visible()
                    box = alert.bounding_box()
                    if box["x"] < 0 or box["x"] + box["width"] > width:
                        found.append(f"logout network-error message outside viewport: {box}; viewport {page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')}")
                if path == "/bill-registers/sales" and width == 320:
                    table = page.get_by_role("table")
                    scroll = table.locator("..")
                    expect(scroll).to_have_attribute("tabindex", "0")
                    scroll.focus()
                    expect(scroll).to_be_focused()
                    scroll.evaluate("el => el.scrollLeft = el.scrollWidth")
                    page.get_by_role("button", name="View bill", exact=False).first.click()
                    expect(page.get_by_role("region", name="Bill PDF view")).to_be_visible()
                    expect(page.get_by_title("PDF of", exact=False)).to_be_visible()
                    found.extend(layout_issues(page, True))
                    page.screenshot(path=str(OUTPUT / "register-preview-320.png"), full_page=True)
                failures.extend(f"{width} {path}: {issue}" for issue in found)
                failures.extend(f"{width} {path}: browser {error}" for error in errors)
                failures.extend(f"{width} {path}: unexpected API {request}" for request in unexpected)
                print(f"Checked {width} {path}: {len(found)} layout issues", flush=True)
                page.close()
        browser.close()
    assert not failures, "\n".join(failures)
    print(f"Passed {len(WIDTHS) * len(PATHS)} responsive page/viewport checks; screenshots: {OUTPUT}")


if __name__ == "__main__":
    main()
