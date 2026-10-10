"""Run against main's built frontend; every API request is isolated and allowlisted.

FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_bill_deletion_ui.py
"""
import json
import os
import re
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright
from billing_test_pdf import blank_a4_pdf
from verify_invoice_financial_year_ui import _mock_api
from verify_invoice_navigation_ui import fill_manual, navigate
from verify_reagent_purchase_order_ui import address, party, totals

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")
KINDS = (("sales", "invoices", "sales"), ("purchase", "purchase-orders", "domestic_oils"),
         ("reagent", "invoices", "reagent"), ("reagent-purchase", "purchase-orders", "reagent"))


def document(collection, kind, ident):
    value = {**totals, "id": ident, "document_type": kind, "branch_id": 1, "version": 3,
             "status": "pdf_generated", "pdf_storage_key": "fixture.pdf", "lines": [],
             "created_by_id": 1, "submitted_revision": 2, "approved_revision": 2}
    if collection == "invoices":
        value.update(invoice_number=f"PBPL/2026-27/{kind.upper()}-{ident:03}",
                     invoice_date="2026-10-06", buyer_name="Fixture buyer")
    else:
        value.update(purchase_order_number=f"CLIENT/{kind.upper()}/PO-{ident:03}",
                     order_date="2026-10-06", purchaser_name="Fixture purchaser", supplier_name="Fixture supplier")
    return value


def number(doc):
    return doc.get("invoice_number", doc.get("purchase_order_number"))


class Fixtures:
    def __init__(self, context, collection, kind, role="admin", count=11):
        self.collection, self.kind, self.role = collection, kind, role
        self.docs = [document(collection, kind, i) for i in range(1, count + 1)]
        self.deleted, self.calls, self.unknown, self.errors, self.pending = {}, [], [], [], []
        self.failure = None
        self.delay = False
        self.next_id = 101
        self.creation_keys = {}
        self.api_base = None
        context.route("**/api/v1/**", self.handle)
        context.on("page", lambda page: page.on("pageerror", lambda error: self.errors.append(str(error))))

    @staticmethod
    def reply(route, value, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(value))

    def complete(self, route, doc, body):
        self.deleted[doc["id"]] = body
        self.docs.remove(doc)
        route.fulfill(status=204, body="")

    def handle(self, route):
        req = route.request
        parsed = urlparse(req.url)
        self.api_base = f"{parsed.scheme}://{parsed.netloc}/api/v1"
        path, method = parsed.path.removeprefix("/api/v1"), req.method
        self.calls.append((method, path))
        if (method, path) == ("GET", "/auth/me"):
            self.reply(route, {"id": 1, "email": "fixture@example.test", "full_name": "Fixture User", "role": self.role,
                               "branch_ids": [], "is_active": True, "password_change_required": False,
                               "mfa_required": False, "mfa_enabled": False, "mfa_verified": True})
        elif (method, path) in (("GET", "/auth/csrf"), ("GET", "/companies/profile")):
            _mock_api(route)  # Exact allowlist only; never delegate unknown paths.
        elif method == "GET" and path == f"/{self.collection}/register":
            query = parse_qs(parsed.query)
            assert query["document_type"] == [self.kind] and query["sort"] == ["date_desc"]
            page, size = int(query["page"][0]), int(query["page_size"][0])
            assert size == 10
            self.reply(route, {"items": self.docs[(page-1)*size:page*size], "total": len(self.docs), "page": page, "page_size": size})
        elif method == "GET" and path in ("/branches", "/purchasers", "/products"):
            self.reply(route, [])
        elif method == "GET" and path == "/customers":
            self.reply(route, [{**party, "billing_address": address, "shipping_address": address}])
        elif method == "GET" and path == "/suppliers":
            self.reply(route, [{**party, "is_default": True}])
        elif method == "GET" and path == "/manufacturers":
            self.reply(route, [{"id": 5, "branch_id": 1, "name": "Merck", "code": "MRK", "is_active": True}])
        elif (method, path) == ("POST", "/invoices/preview"):
            self.reply(route, {**totals, "lines": []})
        elif (method, path) == ("POST", "/invoices") and self.collection == "invoices":
            body = req.post_data_json
            assert body["document_type"] == self.kind
            key = req.headers.get("idempotency-key")
            assert key, "Invoice creation must retain its idempotency intent"
            if key in self.creation_keys:
                original, ident = self.creation_keys[key]
                assert body == original
                if ident in self.deleted:
                    self.reply(route, {"detail": {"code": "document_deleted", "message": "This creation intent belongs to a deleted bill"}}, 410)
                else:
                    self.reply(route, next(d for d in self.docs if d["id"] == ident), 201)
                return
            doc = {**body, **document("invoices", self.kind, self.next_id), "status": "draft", "pdf_storage_key": None}
            self.next_id += 1
            self.creation_keys[key] = (body, doc["id"])
            self.docs.append(doc)
            self.reply(route, doc, 201)
        elif re.fullmatch(rf"/{self.collection}/\d+", path):
            ident = int(path.rsplit("/", 1)[-1])
            doc = next((d for d in self.docs if d["id"] == ident), None)
            if method == "GET":
                self.reply(route, doc if doc else {"detail": "Missing fixture"}, 200 if doc else 404)
            elif method == "DELETE":
                body = req.post_data_json
                assert req.headers.get("x-csrf-token") == "test-csrf", "Use the shared CSRF-aware API"
                if self.failure:
                    status, code, message = self.failure
                    if code == "pdf_cleanup_pending":
                        assert doc is not None
                        assert body == {"expected_version": 3, "confirmation_number": number(doc), "document_type": self.kind}
                        self.deleted[ident] = body; self.docs.remove(doc)
                    self.reply(route, {"detail": {"code": code, "message": message}}, status)
                elif ident in self.deleted:
                    assert body == self.deleted[ident], "Deletion retry must retain the exact contract"
                    route.fulfill(status=204, body="")
                else:
                    assert doc is not None
                    assert body == {"expected_version": 3, "confirmation_number": number(doc), "document_type": self.kind}
                    if self.delay:
                        self.pending.append((route, doc, body))
                    else:
                        self.complete(route, doc, body)
            else:
                self.unknown.append((method, path)); route.abort()
        elif method in ("GET", "POST") and re.fullmatch(rf"/{self.collection}/\d+/(pdf|preview-pdf)", path):
            ident = int(path.split("/")[-2])
            doc = next(d for d in self.docs if d["id"] == ident)
            assert (method, path.rsplit("/", 1)[-1]) == (("GET", "pdf") if doc["pdf_storage_key"] else ("POST", "preview-pdf"))
            if method == "POST":
                assert req.post_data_json == {"expected_version": 3}
            route.fulfill(status=200, content_type="application/pdf", body=blank_a4_pdf())
        else:
            self.unknown.append((method, path)); route.abort()

    def assert_clean(self):
        assert not self.unknown, self.unknown
        assert not self.errors, self.errors


def open_delete(page, bill_number):
    page.get_by_role("button", name=f"Delete bill {bill_number}", exact=True).click()
    dialog = page.get_by_role("dialog", name="Permanently delete bill")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_label("Full bill number", exact=True)).to_be_focused()
    return dialog


def check_register(browser, slug, collection, kind):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    fixture = Fixtures(context, collection, kind)
    page = context.new_page()
    page.set_default_timeout(5000)
    page.goto(f"{BASE_URL}/bill-registers/{slug}")
    expect(page.get_by_role("button", name=re.compile("^Delete bill "))).to_have_count(10)
    page.get_by_role("button", name="Next page").click()
    status = page.get_by_role("status").filter(has_text="Page 2 of 2")
    expect(status).to_contain_text("11 bills")
    bill_number = number(fixture.docs[-1])
    trigger = page.get_by_role("button", name=f"Delete bill {bill_number}", exact=True)
    dialog = open_delete(page, bill_number)
    expect(dialog).to_contain_text("cannot be undone")
    submit = dialog.get_by_role("button", name="Permanently delete", exact=True)
    field = dialog.get_by_label("Full bill number", exact=True)
    for wrong in ("", bill_number.rsplit("/", 1)[-1], bill_number.lower(), f" {bill_number}", f"{bill_number} "):
        field.fill(wrong); expect(submit).to_be_disabled()
    assert not [c for c in fixture.calls if c[0] == "DELETE"]
    field.fill(bill_number)
    expect(submit).to_be_enabled()
    # Native modal keeps the page inert but may let Tab visit browser chrome.
    submit.focus(); page.keyboard.press("Tab")
    assert dialog.evaluate("node => node.open && node.matches(':modal')")
    if not dialog.evaluate("node => node.contains(document.activeElement)"):
        assert page.evaluate("document.activeElement === document.body && !document.hasFocus()"), "Focus escaped to background page content"
        page.keyboard.press("Tab")
    assert dialog.evaluate("node => node.contains(document.activeElement)")
    expect(field).to_be_focused()
    background = page.get_by_role("button", name="Previous page")
    expect(background).to_be_enabled()
    background.evaluate("node => node.focus()")
    expect(field).to_be_focused()  # Enabled background controls remain inert.
    assert dialog.evaluate("node => { const r = node.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth && r.height <= innerHeight; }")
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible(); expect(trigger).to_be_focused()
    dialog = open_delete(page, bill_number)
    dialog.get_by_role("button", name="Cancel", exact=True).click()
    expect(dialog).not_to_be_visible(); expect(trigger).to_be_focused()
    assert not [c for c in fixture.calls if c[0] == "DELETE"]
    page.get_by_role("button", name=f"View bill {bill_number}", exact=True).click()
    viewer = page.get_by_role("region", name="Bill PDF view")
    expect(viewer.locator("iframe")).to_have_count(1)
    dialog = open_delete(page, bill_number)
    field = dialog.get_by_label("Full bill number", exact=True)
    field.fill(bill_number)
    submit = dialog.get_by_role("button", name="Permanently delete", exact=True)
    for failure in ((403, "forbidden", "Admin access required"), (404, "missing", "Bill is missing"),
                    (409, "version_conflict", "Bill version changed"), (409, "confirmation_mismatch", "Confirmation changed"),
                    (409, "document_type_mismatch", "Register type changed"), (409, "linked_payment", "Bill has linked payments"),
                    (409, "linked_integration", "Bill has integration history"), (503, "delete_failed", "Deletion transaction failed"),
                    (503, "invalid_pdf_path", "Stored PDF path is invalid")):
        fixture.failure = failure
        submit.click()
        expect(dialog.get_by_role("alert")).to_contain_text(failure[2])
        expect(submit).to_be_enabled()
        expect(viewer.locator("iframe")).to_have_count(1)
        expect(status).to_contain_text("11 bills")
    fixture.failure = None
    fixture.delay = True
    previous = len([c for c in fixture.calls if c[0] == "DELETE"])
    with page.expect_request(lambda req: req.method == "DELETE"):
        submit.click()
    expect(dialog.get_by_role("button", name="Deleting…", exact=True)).to_be_disabled()
    expect(dialog.get_by_role("button", name="Cancel", exact=True)).to_be_disabled()
    expect(field).to_be_disabled()
    dialog.locator("form").evaluate("node => { node.requestSubmit(); node.requestSubmit(); }")
    page.keyboard.press("Escape"); expect(dialog).to_be_visible()
    assert len([c for c in fixture.calls if c[0] == "DELETE"]) == previous + 1
    route, doc, body = fixture.pending.pop()
    # DB removal with durable private-file cleanup pending must close the view,
    # keep the target and exact text, then retry to obtain an empty-body 204.
    fixture.deleted[doc["id"]] = body; fixture.docs.remove(doc)
    fixture.reply(route, {"detail": {"code": "pdf_cleanup_pending", "message": "Bill removed; PDF cleanup pending. Retry deletion."}}, 503)
    expect(dialog.get_by_role("alert")).to_contain_text("cleanup pending")
    expect(viewer).to_have_count(0)
    expect(field).to_have_value(bill_number)
    expect(page.get_by_role("status").filter(has_text="Permanently deleted")).to_have_count(0)
    submit.click()
    expect(dialog).not_to_be_visible()
    expect(viewer).to_have_count(0)
    expect(page.get_by_role("status").filter(has_text="Page 1 of 1")).to_contain_text("10 bills")
    expect(page.get_by_role("button", name="Next page")).to_be_disabled()
    expect(page.get_by_role("button", name=f"View bill {bill_number}", exact=True)).to_have_count(0)
    expect(page.get_by_role("status").filter(has_text="Permanently deleted")).to_be_focused()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    fixture.assert_clean(); context.close()


def check_sessions(browser, kind):
    context = browser.new_context()
    fixture = Fixtures(context, "invoices", kind, count=0)
    entry_path, label = ("invoices", "Sales invoices") if kind == "sales" else ("reagent-bills", "Reagent bills")
    pages = [context.new_page(), context.new_page()]
    for index, page in enumerate(pages):
        page.set_default_timeout(5000)
        page.goto(f"{BASE_URL}/{entry_path}")
        fill_manual(page, kind)
        if index:
            page.get_by_label("Invoice No.", exact=True).fill(f"{kind}-018")
        page.get_by_role("region", name="Bill submission").get_by_role("button", name="Preview", exact=True).click()
        expect(page.get_by_role("region", name="Bill submission").locator("iframe")).to_have_count(1)
        # First tab leaves entry; second stays mounted to exercise remount recovery.
        if index == 0:
            page.locator("#workspace-content header").get_by_role("link", name=label, exact=True).click()
            expect(page.get_by_role("button", name=re.compile("^Delete bill "))).to_have_count(1)
    pages[0].get_by_role("button", name="Apply filters", exact=True).click()
    expect(pages[0].get_by_role("button", name=re.compile("^Delete bill "))).to_have_count(2)
    for index, target in enumerate([number(doc) for doc in fixture.docs]):
        dialog = open_delete(pages[0], target)
        dialog.get_by_label("Full bill number", exact=True).fill(target)
        fixture.failure = (503, "pdf_cleanup_pending", "Bill removed; PDF cleanup pending")
        dialog.get_by_role("button", name="Permanently delete", exact=True).click()
        expect(dialog.get_by_role("alert")).to_contain_text("cleanup pending")
        expect(dialog.get_by_label("Full bill number", exact=True)).to_have_value(target)
        if index == 0:
            expect(pages[1].get_by_label("Buyer/vendor name", exact=True)).to_have_value(f"Retained {kind} buyer")
            expect(pages[1].get_by_role("region", name="Bill submission").locator("iframe")).to_have_count(1)
        else:
            expect(pages[1].get_by_label("Buyer/vendor name", exact=True)).to_have_value("")
            expect(pages[1].get_by_role("region", name="Bill submission").locator("iframe")).to_have_count(0)
        fixture.failure = None
        dialog.get_by_role("button", name="Permanently delete", exact=True).click()
        expect(dialog).not_to_be_visible()
        expect(pages[0].get_by_role("button", name=f"Delete bill {target}", exact=True)).to_have_count(0)
    # Both same-tab and BroadcastChannel copies must return without the erased
    # draft identity, fields or stale preview/confirmation controls.
    after_deletion = len(fixture.calls)
    for index, page in enumerate(pages):
        if index == 0:
            navigate(page, label)
        expect(page.get_by_label("Buyer/vendor name", exact=True)).to_have_value("")
        expect(page.get_by_label("Invoice No.", exact=True)).to_have_value("")
        panel = page.get_by_role("region", name="Bill submission")
        expect(panel.locator("iframe")).to_have_count(0)
        expect(panel.get_by_role("button", name="Confirm", exact=True)).to_be_disabled()
    assert not [c for c in fixture.calls if c[0] == "PATCH"]
    assert not [c for c in fixture.calls[after_deletion:] if re.match(r"/invoices/(101|102)(/|$)", c[1])], "Navigation must not use erased draft IDs"
    # The still-mounted peer must immediately accept setters and save a fresh
    # draft, without requiring Start new bill or client navigation.
    fill_manual(pages[1], kind)
    pages[1].get_by_label("Invoice No.", exact=True).fill(f"{kind}-019")
    pages[1].get_by_role("region", name="Bill submission").get_by_role("button", name="Preview", exact=True).click()
    expect(pages[1].get_by_role("region", name="Bill submission").locator("iframe")).to_have_count(1)
    assert [doc["id"] for doc in fixture.docs] == [103], "Recovered form must create a fresh draft"
    assert not [c for c in fixture.calls[after_deletion:] if re.match(r"/invoices/(101|102)(/|$)", c[1])], "Recovery must not attempt erased drafts"
    fixture.assert_clean()
    assert pages[0].evaluate("async url => { try { await fetch(url); return false; } catch { return true; } }",
                             f"{fixture.api_base}/__unknown_fixture_probe__")
    assert fixture.unknown == [("GET", "/__unknown_fixture_probe__")], "Unknown API paths must be aborted"
    fixture.unknown.clear()
    fixture.assert_clean(); context.close()


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        for slug, collection, kind in KINDS:
            check_register(browser, slug, collection, kind)
            for role in ("staff", "manager"):
                context = browser.new_context()
                fixture = Fixtures(context, collection, kind, role=role)
                page = context.new_page(); page.set_default_timeout(5000)
                page.goto(f"{BASE_URL}/bill-registers/{slug}")
                expect(page.get_by_role("button", name=re.compile("^View bill "))).to_have_count(10)
                expect(page.get_by_role("button", name=re.compile("^Delete bill "))).to_have_count(0)
                fixture.assert_clean(); context.close()
        for kind in ("sales", "reagent"):
            check_sessions(browser, kind)
        browser.close()
    print("All four Admin registers: exact confirmation, cancel, errors, busy/retry, PDF close, last-page count; Staff/Manager isolation and two-tab invoice invalidation passed.")


if __name__ == "__main__":
    main()
