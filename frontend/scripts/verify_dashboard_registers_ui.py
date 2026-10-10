"""Real dashboard/register UI with isolated HTTP fixtures; no client DB access."""
import json
import os
import re
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright
from billing_test_pdf import blank_a4_pdf
from verify_invoice_financial_year_ui import _mock_api
from verify_reagent_purchase_order_ui import totals

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")
SCREENSHOT_DIR = os.environ.get("REGISTER_SCREENSHOT_DIR")
KINDS = (
    ("sales", "Sales", 2, "invoices", "sales", "Sales bills"),
    ("purchase", "Purchase", 3, "purchase-orders", "domestic_oils", "Purchase bills"),
    ("reagent", "Reagent", 5, "invoices", "reagent", "Reagent bills"),
    ("reagent-purchase", "Reagent Purchase", 7, "purchase-orders", "reagent", "Reagent purchase bills"),
)


def main():
    pdf = blank_a4_pdf()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        for slug, label, count, collection, doc_type, title in KINDS:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(5000)
            errors, calls = [], []
            failures = {"register": False, "pdf": True, "conflict": True, "dashboard": True}
            docs = [{**totals, "id": i, "document_type": doc_type, "version": 3,
                     "status": "pdf_generated" if i == 1 else "draft",
                     "invoice_number": f"PBPL/2026-27/{i:05}", "purchase_order_number": f"PO-{i:05}",
                     "invoice_date": "2026-10-02" if i == 1 else "2026-10-01" if i == 2 else "2026-09-30",
                     "order_date": "2026-10-02" if i == 1 else "2026-10-01" if i == 2 else "2026-09-30",
                     "buyer_name": f"Buyer {i}", "purchaser_name": f"Purchaser {i}", "supplier_name": "Default supplier",
                     "pdf_storage_key": "stored.pdf" if i == 1 else None, "lines": [],
                     "pdf_generated_at": None, "pdf_sha256": None, "pdf_template_version": None,
                     "branch_id": 1, "submitted_revision": None, "approved_revision": None}
                    for i in range(1, 13)]
            # Real API responses are distinct schemas, not a union of both
            # document shapes. Keep type-guard behavior realistic in the UI.
            for document in docs:
                for field in (("purchase_order_number", "order_date", "purchaser_name", "supplier_name") if collection == "invoices" else ("invoice_number", "invoice_date", "buyer_name")):
                    document.pop(field)

            def fulfill(route, value, status=200):
                route.fulfill(status=status, content_type="application/json", body=json.dumps(value))

            def handle(route):
                parsed = urlparse(route.request.url)
                path = parsed.path.removeprefix("/api/v1")
                query = parse_qs(parsed.query)
                if path == "/dashboard":
                    if failures["dashboard"]:
                        failures["dashboard"] = False
                        fulfill(route, {"detail": "Dashboard temporarily unavailable"}, 503)
                        return
                    fulfill(route, {"invoice_count": 7, "sales_invoice_count": 2, "reagent_invoice_count": 5,
                                    "purchase_order_count": 10, "domestic_oils_purchase_order_count": 3,
                                    "reagent_purchase_order_count": 7, "draft_invoices": 9, "draft_purchase_orders": 9,
                                    "pending_invoice_approvals": 9, "pending_purchase_order_approvals": 9, "recent_activity": []})
                elif path == f"/{collection}/register":
                    calls.append((path, query))
                    assert query.get("document_type") == [doc_type]
                    assert query.get("sort") == ["date_desc"]
                    if failures["register"]:
                        failures["register"] = False
                        fulfill(route, {"detail": "Register temporarily unavailable"}, 503)
                        return
                    date_key = "invoice_date" if collection == "invoices" else "order_date"
                    items = [d for d in docs if (not query.get("date_from") or d[date_key] >= query["date_from"][0])
                             and (not query.get("date_to") or d[date_key] <= query["date_to"][0])]
                    number, size = int(query["page"][0]), int(query["page_size"][0])
                    fulfill(route, {"items": items[(number-1)*size:number*size], "total": len(items), "page": number, "page_size": size})
                elif path in (f"/{collection}/1", f"/{collection}/2"):
                    calls.append((path, {}))
                    fulfill(route, docs[int(path.rsplit("/", 1)[-1])-1])
                elif path == f"/{collection}/1/pdf":
                    calls.append((path, {}))
                    if failures["pdf"]:
                        failures["pdf"] = False
                        fulfill(route, {"detail": "Stored PDF temporarily unavailable"}, 503)
                    else:
                        route.fulfill(status=200, content_type="application/pdf", body=pdf)
                elif path == f"/{collection}/2/preview-pdf":
                    calls.append((path, route.request.post_data_json))
                    assert route.request.post_data_json == {"expected_version": docs[1]["version"]}
                    if failures["conflict"]:
                        failures["conflict"] = False
                        docs[1]["version"] = 4
                        fulfill(route, {"detail": {"code": "version_conflict", "message": "This draft changed. Retry to view its latest revision."}}, 409)
                    else:
                        route.fulfill(status=200, content_type="application/pdf", body=pdf)
                else:
                    assert not any(path.endswith("/" + action) for action in ("approve", "submit", "generate-pdf", "amend")), "View must not mutate a bill"
                    _mock_api(route)

            page.route("**/api/v1/**", handle)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(BASE_URL)
            cards = page.get_by_role("region", name="Saved bill registers")
            expect(cards).to_be_visible()
            expect(cards.get_by_role("alert")).to_contain_text("Dashboard temporarily unavailable")
            expect(cards.get_by_role("link")).to_have_count(4)
            expect(page.get_by_role("region", name="Choose a bill type").get_by_role("link")).to_have_count(4)
            page.get_by_role("button", name="Retry loading", exact=True).click()
            for _, card_label, card_count, _, _, _ in KINDS:
                expect(cards.get_by_role("link", name=re.compile(rf"^{card_label}\s+{card_count}\b"))).to_be_visible()
            for removed in ("Draft invoices", "Invoice approvals", "Draft purchase orders", "PO approvals", "Recent activity"):
                expect(page.get_by_text(removed, exact=True)).to_have_count(0)
            if SCREENSHOT_DIR and slug == "sales":
                page.screenshot(path=f"{SCREENSHOT_DIR}/dashboard.png", full_page=True)
            cards.get_by_role("link", name=re.compile(rf"^{label}\s+{count}\b")).click()
            expect(page).to_have_url(f"{BASE_URL}/bill-registers/{slug}")
            expect(page.get_by_role("heading", name=title, exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="Next page")).to_be_enabled()
            page.get_by_role("button", name="Next page").click()
            expect(page.get_by_role("status").filter(has_text="Page 2")).to_be_visible()
            expect(page.get_by_role("status").filter(has_text="Page 2")).to_be_focused()
            page.get_by_label("Date filter", exact=True).select_option("date")
            page.get_by_label("Bill date", exact=True).fill("2026-10-01")
            page.get_by_role("button", name="Apply filters", exact=True).click()
            expect(page.get_by_role("status").filter(has_text="01 Oct 2026")).to_be_visible()
            expect(page.get_by_role("button", name=re.compile(r"^View bill "))).to_have_count(1)
            expected_number = "PBPL/2026-27/00002" if collection == "invoices" else "PO-00002"
            page.get_by_role("button", name=f"View bill {expected_number}", exact=True).click()
            viewer = page.get_by_role("region", name="Bill PDF view")
            expect(viewer.get_by_role("alert")).to_contain_text("draft changed")
            viewer.get_by_role("button", name="Retry PDF").click()
            expect(viewer.get_by_text("Draft preview", exact=True)).to_be_visible()
            expect(viewer.locator("iframe")).to_have_count(1)
            viewer.get_by_role("button", name="Close view").click()
            page.get_by_label("Date filter", exact=True).select_option("range")
            page.get_by_label("From date", exact=True).fill("2026-10-02")
            page.get_by_label("To date", exact=True).fill("2026-10-01")
            previous_calls = len(calls)
            page.get_by_role("button", name="Apply filters", exact=True).click()
            expect(page.get_by_text("End date must be on or after start date", exact=True)).to_be_visible()
            assert len(calls) == previous_calls
            page.get_by_label("From date", exact=True).fill("2026-10-01")
            page.get_by_label("To date", exact=True).fill("2026-10-02")
            page.get_by_role("button", name="Apply filters", exact=True).click()
            expect(page.get_by_role("button", name=re.compile(r"^View bill "))).to_have_count(2)
            if SCREENSHOT_DIR and slug == "sales":
                page.screenshot(path=f"{SCREENSHOT_DIR}/sales-register.png", full_page=True)
            page.get_by_role("button", name=re.compile(r"^View bill ")).first.click()
            expect(viewer.get_by_role("alert")).to_contain_text("Stored PDF temporarily unavailable")
            viewer.get_by_role("button", name="Retry PDF").click()
            expect(viewer.get_by_text("Saved PDF", exact=True)).to_be_visible()
            expect(viewer.locator("iframe")).to_have_count(1)
            viewer.get_by_role("button", name="Close view").click()
            page.get_by_label("From date", exact=True).fill("2027-01-01")
            page.get_by_label("To date", exact=True).fill("2027-01-31")
            page.get_by_role("button", name="Apply filters", exact=True).click()
            expect(page.get_by_text("No bills match these dates.", exact=True)).to_be_visible()
            failures["register"] = True
            page.get_by_role("button", name="Clear filters", exact=True).click()
            expect(page.get_by_role("region", name="Saved bills").get_by_role("alert")).to_contain_text("Register temporarily unavailable")
            page.get_by_role("button", name="Retry loading", exact=True).click()
            expect(page.get_by_role("button", name=re.compile(r"^View bill "))).to_have_count(10)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            if SCREENSHOT_DIR and slug == "sales":
                page.screenshot(path=f"{SCREENSHOT_DIR}/sales-register-mobile.png", full_page=True)
            assert not errors, errors
            page.close()
        browser.close()
    print("Four dashboard counts/register links, type isolation, dates/ranges, validation, pagination, PDF view/retry, empty/error states and mobile width passed.")


if __name__ == "__main__":
    main()
