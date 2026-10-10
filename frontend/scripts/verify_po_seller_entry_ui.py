"""PO seller/shipping entry regressions with isolated browser API fixtures."""
import json
import os
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
from verify_invoice_financial_year_ui import _mock_api
from verify_reagent_purchase_order_ui import party, totals


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for path, saved_mode in ((path, mode) for path in ("purchase-orders", "reagent-purchase-orders") for mode in (False, True)):
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.set_default_timeout(7000)
                suppliers = [{**party, "name": "Default Seller", "is_default": True}, {**party, "id": 2, "name": "Selected Seller", "phone": "9876500000", "email": "seller@example.org", "is_default": False, "address": {**party["address"], "address_line1": "Selected Seller Road"}}]
                saves, previews, errors, edits, documents = [], [], [], [], []
                reject_email = [not saved_mode]
                reject_dispatch = [path == "purchase-orders"]
                fail_save = [True]

                def respond(route, value, status=200):
                    route.fulfill(status=status, content_type="application/json", body=json.dumps(value))

                def api(route):
                    endpoint = urlparse(route.request.url).path.removeprefix("/api/v1")
                    if endpoint == "/suppliers": respond(route, suppliers)
                    elif endpoint == "/purchasers": respond(route, [party])
                    elif endpoint == "/manufacturers": respond(route, [{"id": 5, "branch_id": 1, "name": "Merck", "code": "MRK", "is_active": True}])
                    elif endpoint == "/purchase-orders/preview":
                        previews.append(route.request.post_data_json)
                        respond(route, {**totals, "lines": [{**route.request.post_data_json["lines"][0], **totals}]})
                    elif endpoint == "/purchase-orders" and route.request.method == "POST":
                        body = route.request.post_data_json
                        saves.append((route.request.headers.get("idempotency-key"), body))
                        if reject_email[0]:
                            reject_email[0] = False
                            respond(route, {"detail": [{"loc": ["body", "supplier", "email"], "msg": "Enter a valid seller email"}]}, 422)
                        elif reject_dispatch[0]:
                            reject_dispatch[0] = False
                            respond(route, {"detail": [{"loc": ["body", "transport_mode"], "msg": "Enter a valid dispatch method"}]}, 422)
                        elif fail_save[0]:
                            fail_save[0] = False
                            respond(route, {"detail": "Temporary save failure. Retry."}, 503)
                        else:
                            supplier = body.get("supplier", suppliers[1])
                            document = {**body, **totals, "id": 101, "branch_id": 1, "version": 1, "status": "draft", "supplier_id": body.get("supplier_id", 3), "purchase_order_number": "ENTRY-PO-001", "created_by_id": 1, "pdf_storage_key": None, "lines": [{**body["lines"][0], "id": 1, "product_id": 7, "product_name": body["lines"][0].get("product_name", "Reagent"), "description": body["lines"][0].get("description") or "", "sort_order": 1, **totals}]}
                            document.update({f"supplier_{key}": supplier.get(key) for key in ("name", "gstin", "pan", "phone", "email")})
                            document.update({f"supplier_{key}": value for key, value in supplier["address"].items() if key != "name"})
                            documents.append(document)
                            respond(route, document, 201)
                    elif endpoint == "/purchase-orders/101" and route.request.method == "PATCH":
                        body = route.request.post_data_json
                        edits.append(body)
                        document = {**documents[-1], **body["domestic_details"], "version": documents[-1]["version"] + 1}
                        documents.append(document)
                        respond(route, document)
                    else: _mock_api(route)

                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/api/v1/**", api)
                page.goto(f'{os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")}/{path}')
                seller = page.get_by_role("region", name="Seller", exact=True)
                shipping = page.get_by_role("region", name="Seller / Shipping Address", exact=True)
                expect(seller.get_by_role("heading", name="Seller", exact=True)).to_be_visible()
                expect(shipping).to_contain_text("Default Seller")
                assert seller.get_by_role("heading").first.evaluate("el => getComputedStyle(el).fontWeight") == "700"
                assert shipping.get_by_role("heading").evaluate("el => getComputedStyle(el).fontWeight") == "700"
                page.get_by_label("Saved seller", exact=True).select_option("2")
                for value in ("Selected Seller", "Selected Seller Road", "9876500000", "seller@example.org"):
                    expect(shipping).to_contain_text(value)
                page.get_by_label("Saved seller", exact=True).select_option("")
                for label, value in (("Seller company name", "Manual Seller"), ("GSTIN", "36ABCDE1234F1Z5"), ("PAN", "ABCDE1234F"), ("Contact (phone)", "9000001234"), ("Email", "manual@example.org"), ("Address line 1", "Manual Seller Road"), ("City", "Hyderabad"), ("State", "Telangana"), ("State code", "36"), ("Postal code", "500001")):
                    seller.get_by_label(label, exact=True).fill(value)
                for value in ("Manual Seller", "Manual Seller Road", "36ABCDE1234F1Z5", "9000001234", "manual@example.org"):
                    expect(shipping).to_contain_text(value)
                if saved_mode:
                    page.get_by_label("Saved seller", exact=True).select_option("2")
                    expect(seller.get_by_label("Contact (phone)", exact=True)).to_have_value("9876500000")
                    expect(seller.get_by_label("Email", exact=True)).to_have_value("seller@example.org")
                assert shipping.get_by_role("textbox").count() == 0
                assert page.get_by_label("Consignee same as purchaser", exact=True).count() == 0
                expect(page.get_by_role("button", name="Use saved purchaser", exact=True)).to_have_count(0)
                expect(page.get_by_label("Saved purchaser", exact=True)).to_have_count(0)
                expect(page.get_by_role("heading", name="Purchaser company", exact=True)).to_have_count(0)
                expect(page.get_by_role("heading", name="Purchaser / buyer details", exact=True)).to_have_count(0)
                page.get_by_label("PO No.", exact=True).fill("ENTRY-PO-001")
                if path == "purchase-orders":
                    dispatch = page.get_by_label("Dispatched through", exact=True)
                    expect(dispatch).to_be_visible()
                    assert dispatch.get_attribute("maxlength") == "100"
                    dispatch.fill("  ROAD / Courier  ")
                page.get_by_label("Material name" if path == "purchase-orders" else "Product name", exact=True).fill("Test material")
                page.get_by_label("HSN/SAC", exact=True).fill("29181590")
                page.get_by_label("Rate", exact=True).fill("100.00")
                if path == "reagent-purchase-orders": page.get_by_label("Manufacturer", exact=True).select_option("5")
                expect(page.get_by_role("heading", name="Live backend preview", exact=True)).to_be_visible()
                save = page.get_by_role("button", name="Save purchase order" if path == "purchase-orders" else "Save reagent purchase order", exact=True)
                if not saved_mode:
                    save.click()
                    expect(seller.get_by_text("Enter a valid seller email", exact=True)).to_be_visible()
                    expect(seller.get_by_label("Email", exact=True)).to_have_value("manual@example.org")
                if path == "purchase-orders":
                    save.click()
                    expect(page.get_by_text("Enter a valid dispatch method", exact=True)).to_be_visible()
                    expect(dispatch).to_have_value("  ROAD / Courier  ")
                    dispatch.fill("ROAD / Courier")
                    expect(page.get_by_text("Enter a valid dispatch method", exact=True)).to_have_count(0)
                save.click()
                expect(page.get_by_role("alert").filter(has_text="Temporary save failure")).to_be_visible()
                save.click()
                expect(page.get_by_label("Saved seller", exact=True)).to_be_disabled()
                assert saves[-1] == saves[-2], "Retry changed the intended key/payload"
                if path == "purchase-orders":
                    assert saves[-1][1]["transport_mode"] == "ROAD / Courier"
                    expect(dispatch).to_have_value("ROAD / Courier")
                assert not {"purchaser", "purchaser_id", "save_purchaser_for_future"}.intersection(saves[-1][1]), "Removed purchaser fields leaked into the save"
                if saved_mode:
                    assert saves[-1][1]["supplier_id"] == 2, "Default seller replaced the selected seller"
                    assert "supplier" not in saves[-1][1]
                    expect(shipping).to_contain_text("Selected Seller Road")
                else:
                    assert saves[-1][1]["supplier"]["phone"] == "9000001234"
                    assert saves[-1][1]["supplier"]["email"] == "manual@example.org"
                    assert "supplier_id" not in saves[-1][1], "Default seller silently replaced manual input"
                    expect(shipping).to_contain_text("Manual Seller Road")
                if path == "purchase-orders":
                    dispatch.fill("RAIL")
                    with page.expect_response(lambda response: urlparse(response.url).path.endswith("/purchase-orders/101") and response.request.method == "PATCH") as updated:
                        save.click()
                    assert updated.value.status == 200
                    assert edits[-1]["expected_version"] == 1
                    assert edits[-1]["domestic_details"]["transport_mode"] == "RAIL"
                    expect(dispatch).to_have_value("RAIL")
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert not errors, errors
                page.close()
                print(f"{path} ({'saved' if saved_mode else 'manual'}): Seller/shipping, contact/email, dispatch save/edit where applicable, stable retry and mobile passed")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
