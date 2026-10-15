"""Optional real frontend + FastAPI contract, using only in-memory test data.

Set FRONTEND_INTEGRATION_URL to a local frontend. Browser API requests are
transported to TestClient (real validation/calculation/permissions/workflows),
never a client database. Only expensive PDF rendering uses a valid fixture PDF.
"""
import hashlib
import importlib.util
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.services.invoice_pdf import PdfGenerationResult
from tests.test_confirmed_bill_corrections import confirmed
from tests.test_inline_submission import DOCUMENTS


@pytest.mark.parametrize("kind", DOCUMENTS)
def test_browser_staff_correction_is_reviewed_and_published_by_independent_manager(
    kind, client, auth_headers, staff_user, manager_user, admin_user, branch, db_session, monkeypatch, tmp_path,
):
    frontend = os.environ.get("FRONTEND_INTEGRATION_URL")
    if not frontend:
        pytest.skip("FRONTEND_INTEGRATION_URL not configured (local browser contract only)")
    if urlsplit(frontend).hostname not in {"localhost", "127.0.0.1"}:
        pytest.fail("Refusing non-local browser integration URL")
    from playwright.sync_api import expect, sync_playwright

    url, original, _, _, key, old_pdf = confirmed(kind, client, auth_headers, admin_user, admin_user, branch, db_session, monkeypatch, tmp_path)
    fixture_file = Path(__file__).resolve().parents[2] / "frontend/scripts/billing_test_pdf.py"
    spec = importlib.util.spec_from_file_location("billing_pdf_fixture", fixture_file)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    pdf = fixture.blank_a4_pdf()
    monkeypatch.setattr("app.api.v1.invoices.render_invoice_pdf", lambda context: PdfGenerationResult(pdf, hashlib.sha256(pdf).hexdigest()))
    monkeypatch.setattr("app.api.v1.purchase_orders.render_purchase_order_pdf", lambda context: PdfGenerationResult(pdf, hashlib.sha256(pdf).hexdigest()))
    is_po = "purchase-orders" in url
    entry = {"sales": "invoices", "reagent_bill": "reagent-bills", "domestic_oils": "purchase-orders", "reagent_po": "reagent-purchase-orders"}[kind]
    register = {"sales": "sales", "reagent_bill": "reagent", "domestic_oils": "purchase", "reagent_po": "reagent-purchase"}[kind]
    parameter = "order" if is_po else "invoice"
    errors = []

    def context_for(browser, actor):
        context = browser.new_context()
        actor_headers = auth_headers(actor)

        def transport(route):
            request = route.request
            parsed = urlsplit(request.url)
            path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            headers = dict(actor_headers)
            if request.headers.get("content-type"):
                headers["Content-Type"] = request.headers["content-type"]
            response = client.request(request.method, path, headers=headers, content=request.post_data_buffer)
            headers = {name: value for name, value in response.headers.items() if name.lower() not in {"content-length", "set-cookie"}}
            headers.update({"access-control-allow-origin": frontend.rstrip("/"), "access-control-allow-credentials": "true"})
            route.fulfill(status=response.status_code, headers=headers, body=response.content)

        context.route("**/api/v1/**", transport)
        return context

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = context_for(browser, staff_user)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        number = "purchase_order_number" if is_po else "invoice_number"
        page.goto(f"{frontend}/bill-registers/{register}")
        page.get_by_role("link", name=f"Edit bill {original[number]}", exact=True).click()
        expect(page).to_have_url(f"{frontend}/{entry}?{parameter}={original['id']}&correction=1")
        panel = page.get_by_role("region", name="Bill submission", exact=True)
        quantity = page.get_by_label("Quantity", exact=True).first
        expect(quantity).to_have_value(original["lines"][0]["quantity"])
        expect(page.get_by_label("PO No." if is_po else "Invoice No.", exact=True)).to_have_value(original[number] if is_po else original[number].split("/", 2)[-1])
        expect(page.get_by_label("Seller company name" if is_po else "Buyer/vendor name", exact=True)).to_have_value(original["supplier_name" if is_po else "buyer_name"])
        expect(page.get_by_role("textbox", name="Address line 1", exact=True).first).to_have_value(original["supplier_address_line1" if is_po else "buyer_address_line1"])
        expect(page.get_by_label("GSTIN", exact=True).first).to_have_value(original["supplier_gstin" if is_po else "buyer_gstin"] or "")
        expect(page.get_by_role("textbox", name="Material name" if kind == "domestic_oils" else "Product name", exact=True).first).to_have_value(original["lines"][0]["product_name"])
        expect(page.get_by_label("HSN/SAC", exact=True).first).to_have_value(original["lines"][0]["hsn_sac"])
        expect(page.get_by_label("Rate", exact=True).first).to_have_value(original["lines"][0]["rate"])
        quantity.fill("2")
        panel.get_by_label("Correction reason", exact=True).fill("Correct quantity entered by mistake")
        panel.get_by_role("button", name="Preview", exact=True).click()
        try:
            expect(panel.get_by_title("Bill PDF preview", exact=True)).to_be_visible()
        except AssertionError as exc:
            raise AssertionError(panel.inner_text()) from exc
        panel.get_by_role("button", name="Confirm", exact=True).click()
        expect(panel).to_contain_text("Submitted for approval")
        assert client.get(url, headers=auth_headers(staff_user)).json()["lines"][0]["quantity"] == original["lines"][0]["quantity"]
        context.close()

        context = context_for(browser, manager_user)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{frontend}/approvals")
        queue = page.get_by_role("region", name="Confirmed bill corrections", exact=True)
        queue.get_by_role("link", name="Review correction", exact=True).click()
        panel = page.get_by_role("region", name="Bill submission", exact=True)
        expect(page.get_by_label("Quantity", exact=True).first).to_have_value("2.000")
        expect(panel.get_by_role("button", name="Confirm", exact=True)).to_be_disabled()
        panel.get_by_role("button", name="Preview", exact=True).click()
        expect(panel.get_by_title("Bill PDF preview", exact=True)).to_be_visible()
        panel.get_by_role("button", name="Confirm", exact=True).click()
        expect(panel.get_by_role("button", name="Download", exact=True)).to_be_enabled(timeout=15000)
        expect(panel).to_contain_text("Bill confirmed")
        expect(page).to_have_url(f"{frontend}/{entry}?{parameter}={original['id']}")
        expect(page.get_by_label("Quantity", exact=True).first).to_be_disabled()
        latest = client.get(url, headers=auth_headers(manager_user)).json()
        number = "purchase_order_number" if is_po else "invoice_number"
        assert latest["id"] == original["id"]
        assert latest[number] == original[number]
        assert latest["lines"][0]["quantity"] == "2.000"
        assert latest["pdf_storage_key"] != key
        assert (tmp_path / key).read_bytes() == old_pdf
        assert client.get(url + "/pdf", headers=auth_headers(manager_user)).content == pdf
        assert not errors
        context.close()
        browser.close()
