"""Submission-panel browser regressions; API fixtures do not replace backend tests."""
import json
import os
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
from verify_invoice_financial_year_ui import _mock_api
from verify_reagent_purchase_order_ui import party, totals
from billing_test_pdf import blank_a4_pdf

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")


def main():
    pdf = blank_a4_pdf()
    with sync_playwright() as playwright:
        # Full Chromium/new headless supports the native PDF viewer. The default
        # headless shell does not load embedded PDF documents or emit their load.
        browser = playwright.chromium.launch(channel="chromium")
        for page_path in ("invoices", "reagent-bills", "purchase-orders", "reagent-purchase-orders"):
            for role in ("admin", "staff", "manager"):
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.set_default_timeout(6000)
                documents, attempts, previews, errors, creation_keys = [], [], [], [], {}
                patches, actions, failures = [], [], {"create": True, "pdf": True, "patch": True, "generate": True, "submit_response": True, "approve_response": True}
                collection = "/invoices" if page_path in ("invoices", "reagent-bills") else "/purchase-orders"
                is_reagent = page_path in ("reagent-bills", "reagent-purchase-orders")

                def fulfill(route, value, status=200):
                    route.fulfill(status=status, content_type="application/json", body=json.dumps(value))

                def handle(route):
                    path = urlparse(route.request.url).path.removeprefix("/api/v1")
                    method = route.request.method
                    if path == "/auth/me":
                        fulfill(route, {"id": 1, "email": "user@example.test", "full_name": "Bill maker", "role": role, "branch_ids": [1], "is_active": True, "mfa_verified": True, "mfa_required": False, "password_change_required": False})
                    elif path == "/suppliers": fulfill(route, [{**party, "is_default": True}])
                    elif path == "/purchasers": fulfill(route, [party])
                    elif path == "/manufacturers": fulfill(route, [{"id": 5, "branch_id": 1, "name": "Merck", "code": "MRK", "is_active": True}])
                    elif path.endswith("/preview"):
                        fulfill(route, {**totals, "lines": [{**route.request.post_data_json["lines"][0], **totals}]})
                    elif path == collection and method == "POST":
                        if is_reagent and route.request.post_data_json["lines"][0]["pack_size"] == "Rejected pack":
                            fulfill(route, {"detail": [{"loc": ["body", "lines", 0, "pack_size"], "msg": "Pack/Size validation failed"}]}, 422)
                            return
                        attempts.append((route.request.headers.get("idempotency-key"), route.request.post_data_json))
                        key, body = attempts[-1]
                        if key in creation_keys:
                            assert body == creation_keys[key]["payload"], "Same key must replay the exact original payload"
                            fulfill(route, creation_keys[key]["document"], 201)
                            return
                        if documents:
                            fulfill(route, {"detail": "Duplicate document number after an uncertain save"}, 409)
                            return
                        document = {**body, **totals, "id": 101, "branch_id": 1, "version": 1, "status": "draft", "invoice_number": "PBPL/2026-27/TEST-001", "purchase_order_number": "TEST-PO-001", "created_by_id": 1, "submitted_by_id": None, "pdf_storage_key": None}
                        if collection == "/purchase-orders":
                            assert not {"purchaser", "purchaser_id", "save_purchaser_for_future"}.intersection(body)
                            supplier = body.get("supplier", party)
                            document.update({f"supplier_{field}": supplier.get(field) for field in ("name", "gstin", "pan", "phone", "email")})
                            document.update({f"supplier_{field}": value for field, value in supplier["address"].items() if field != "name"})
                            document["supplier_id"] = body.get("supplier_id", 1)
                        documents.append(document)
                        creation_keys[key] = {"payload": body, "document": document}
                        if failures["create"]:
                            failures["create"] = False
                            fulfill(route, {"detail": "Network save interrupted. Retry without losing fields."}, 503)
                        else:
                            fulfill(route, document, 201)
                    elif path == f"{collection}/101" and method == "PATCH":
                        patches.append(route.request.post_data_json)
                        body = patches[-1].get("domestic_details", patches[-1].get("reagent_details", patches[-1]))
                        if failures["patch"] and body["lines"][0].get("product_name") == "Edited Product":
                            failures["patch"] = False
                            fulfill(route, {"detail": {"code": "version_conflict", "message": "Another user changed this revision."}}, 409)
                        else:
                            assert patches[-1]["expected_version"] == documents[0]["version"]
                            documents[0].update(body)
                            documents[0]["version"] += 1
                            fulfill(route, documents[0])
                    elif path == f"{collection}/101" and method == "GET": fulfill(route, documents[0])
                    elif path.endswith("/preview-pdf"):
                        previews.append(route.request.post_data_json)
                        if failures["pdf"]:
                            failures["pdf"] = False
                            fulfill(route, {"detail": "PDF preview temporarily unavailable"}, 503)
                        else:
                            assert previews[-1]["expected_version"] == documents[0]["version"]
                            route.fulfill(status=200, content_type="application/pdf", body=pdf)
                    elif path.endswith("/pdf"):
                        assert documents[0]["pdf_storage_key"]
                        route.fulfill(status=200, content_type="application/pdf", body=pdf)
                    elif path.startswith(f"{collection}/101/"):
                        action = path.rsplit("/", 1)[-1]
                        actions.append(action)
                        if action == "submit":
                            assert route.request.post_data_json["expected_version"] == documents[0]["version"]
                            documents[0].update(status="pending_approval", submitted_by_id=1, submitted_revision=documents[0]["version"], version=documents[0]["version"] + 1)
                            if failures["submit_response"]:
                                failures["submit_response"] = False
                                fulfill(route, {"detail": "Submission response lost after commit"}, 503)
                                return
                        elif action == "approve":
                            assert role == "admin", "Staff confirmation must not bypass approval"
                            assert route.request.post_data_json["expected_version"] == documents[0]["version"]
                            documents[0].update(status="approved", approved_revision=documents[0]["submitted_revision"], version=documents[0]["version"] + 1)
                            if failures["approve_response"]:
                                failures["approve_response"] = False
                                fulfill(route, {"detail": "Approval response lost after commit"}, 503)
                                return
                        elif action == "generate-pdf":
                            if failures["generate"]:
                                failures["generate"] = False
                                fulfill(route, {"detail": "Final PDF unavailable; retry confirmation"}, 503)
                                return
                            assert documents[0]["status"] == "approved"
                            documents[0].update(pdf_storage_key="stored.pdf", status="pdf_generated" if collection == "/invoices" else "approved")
                        fulfill(route, documents[0])
                    else: _mock_api(route)

                page.route("**/api/v1/**", handle)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"{BASE_URL}/{page_path}")
                panel = page.get_by_role("region", name="Bill submission", exact=True)
                expect(panel).to_be_visible()
                for label in ("Preview", "Edit", "Download", "Print", "Confirm"):
                    expect(panel.get_by_role("button", name=label, exact=True)).to_be_visible()
                expect(panel.get_by_role("button", name="Download", exact=True)).to_be_disabled()
                expect(panel.get_by_role("button", name="Print", exact=True)).to_be_disabled()
                live = page.get_by_role("heading", name="Live backend preview", exact=True)
                assert live.bounding_box()["y"] < panel.bounding_box()["y"]
                if collection == "/invoices":
                    for label, value in (("Buyer/vendor name", "Buyer company"), ("Address line 1", "New buyer street"), ("City", "Hyderabad"), ("State", "Telangana"), ("Postal code", "500001"), ("Invoice No.", "TEST-001"), ("Product name", "Test Product"), ("HSN/SAC", "29181590"), ("Rate", "100.00")):
                        page.get_by_label(label, exact=True).fill(value)
                    if page_path == "reagent-bills":
                        page.get_by_role("combobox", name="MFG / Manufacturer", exact=True).select_option("5")
                        page.get_by_label("Item Description", exact=True).fill("Reagent product")
                    product_label = "Product name"
                elif page_path == "purchase-orders":
                    for label, value in (("PO No.", "TEST-PO-001"), ("Material name", "Test Product"), ("HSN/SAC", "29181590"), ("Rate", "100.00")):
                        page.get_by_label(label, exact=True).fill(value)
                    product_label = "Material name"
                else:
                    for label, value in (("PO No.", "TEST-PO-001"), ("Product name", "Test Product"), ("HSN/SAC", "29181590"), ("Rate", "100.00")):
                        page.get_by_label(label, exact=True).fill(value)
                    page.get_by_role("combobox", name="Manufacturer", exact=True).select_option("5")
                    product_label = "Product name"
                preview = panel.get_by_role("button", name="Preview", exact=True)
                if is_reagent:
                    pack = page.get_by_role("textbox", name="Pack/Size", exact=True)
                    expect(pack).to_have_attribute("maxlength", "100")
                    pack.fill("Rejected pack")
                    preview.click()
                    expect(pack).to_have_attribute("aria-invalid", "true")
                    error_id = pack.get_attribute("aria-describedby")
                    expect(page.locator(f'[id="{error_id}"]')).to_have_text("Pack/Size validation failed")
                    pack.fill("500 g")
                else:
                    expect(page.get_by_role("textbox", name="Pack/Size", exact=True)).to_have_count(0)
                preview.click()
                expect(panel.get_by_role("alert")).to_contain_text("Network save interrupted")
                expect(page.get_by_role("textbox", name=product_label, exact=True)).to_have_value("Test Product")
                # Edit after a committed creation lost its response: resolve the
                # original intent before applying this to the same document.
                page.get_by_role("textbox", name="Payment terms", exact=True).fill("45 days")
                preview.click()
                expect(panel.get_by_role("alert")).to_contain_text("PDF preview temporarily unavailable")
                assert attempts[0] == attempts[1], "Creation retry must retain payload/key"
                if is_reagent:
                    assert attempts[0][1]["lines"][0]["pack_size"] == "500 g"
                    expect(page.get_by_role("textbox", name="Pack/Size", exact=True)).to_have_value("500 g")
                preview.click()
                expect(panel.locator('iframe[title="Bill PDF preview"]')).to_have_count(1)
                assert len(documents) == 1 and len(attempts) == 2
                assert len(page.context.pages) == 1, "Preview must remain inside the entry page"
                expect(page.get_by_role("textbox", name=product_label, exact=True)).to_be_disabled()
                expect(panel.get_by_role("button", name="Confirm", exact=True)).to_be_enabled()
                panel.get_by_role("button", name="Edit", exact=True).click()
                expect(panel.locator("iframe")).to_have_count(0)
                expect(page.get_by_role("textbox", name=product_label, exact=True)).to_be_editable()
                page.get_by_role("textbox", name=product_label, exact=True).fill("Edited Product")
                if is_reagent:
                    page.get_by_role("textbox", name="Pack/Size", exact=True).fill("10 × 2 mL")
                expect(panel.get_by_role("button", name="Confirm", exact=True)).to_be_disabled()
                preview.click()
                expect(panel.get_by_role("alert")).to_contain_text("Another user changed")
                expect(page.get_by_role("textbox", name=product_label, exact=True)).to_have_value("Edited Product")
                preview.click()
                expect(panel.locator("iframe")).to_have_count(1)
                assert len(attempts) == 2 and len(documents) == 1 and len(patches) == 3
                if is_reagent:
                    assert documents[0]["lines"][0]["pack_size"] == "10 × 2 mL"
                panel.get_by_role("button", name="Confirm", exact=True).click()
                if role == "admin":
                    expect(panel.get_by_role("alert")).to_contain_text("Final PDF unavailable")
                    panel.get_by_role("button", name="Confirm", exact=True).click()
                else:
                    expect(panel.get_by_role("status")).to_contain_text("approval")
                    expect(panel.get_by_role("button", name="Download", exact=True)).to_be_disabled()
                    assert "approve" not in actions
                    documents[0].update(status="approved", pdf_storage_key="stored.pdf")
                    panel.get_by_role("button", name="Check approval", exact=True).click()
                expect(panel.get_by_role("button", name="Download", exact=True)).to_be_enabled()
                expect(panel.get_by_role("button", name="Edit", exact=True)).to_be_disabled()
                with page.expect_download() as downloaded:
                    panel.get_by_role("button", name="Download", exact=True).click()
                assert downloaded.value.suggested_filename.endswith(".pdf")
                # Test invoking print on the PDF frame rather than the entry document.
                expect(panel.locator("iframe")).to_have_attribute("data-ready", "true")
                page.evaluate("() => { window.print = () => {throw new Error('Must not print billing entry form')}; }")
                page.evaluate("() => { document.querySelector('iframe[title=\"Bill PDF preview\"]').contentWindow.print = () => { window.pdfPrintRequested = true; }; }")
                panel.get_by_role("button", name="Print", exact=True).click()
                page.wait_for_function("window.pdfPrintRequested === true")
                expect(panel.get_by_role("button", name="Start new bill", exact=True)).to_be_enabled()
                assert len(page.context.pages) == 1
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                assert not errors, errors
                page.close()
        browser.close()
    print("All four bill types/admin+staff+manager: inline preview, recoverable retries, same-draft edit/conflict, approval-safe Confirm, download/print and mobile passed.")


if __name__ == "__main__":
    main()
