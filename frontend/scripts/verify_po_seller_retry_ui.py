"""Recover the fixed seller after a committed creation response is lost."""
import json
import os
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
from verify_invoice_financial_year_ui import _mock_api
from verify_reagent_purchase_order_ui import party, totals
from verify_bill_session_customer_ui import navigate


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for path in ("purchase-orders", "reagent-purchase-orders"):
                page = browser.new_page()
                page.set_default_timeout(6000)
                document, posts, patches = [], [], []
                suppliers = [{**party, "name": "Default Seller", "is_default": True}, {**party, "id": 2, "name": "Original Seller", "is_default": False}]

                def fulfill(route, value, status=200):
                    route.fulfill(status=status, content_type="application/json", body=json.dumps(value))

                def handle(route):
                    endpoint = urlparse(route.request.url).path.removeprefix("/api/v1")
                    body = route.request.post_data_json if route.request.method in ("POST", "PATCH") else None
                    if endpoint == "/suppliers": fulfill(route, suppliers)
                    elif endpoint == "/purchasers": fulfill(route, [party])
                    elif endpoint == "/manufacturers": fulfill(route, [{"id": 5, "branch_id": 1, "name": "Merck", "code": "MRK", "is_active": True}])
                    elif endpoint == "/purchase-orders/preview": fulfill(route, {**totals, "lines": [{**body["lines"][0], **totals}]})
                    elif endpoint == "/purchase-orders" and route.request.method == "POST":
                        posts.append((route.request.headers.get("idempotency-key"), body))
                        if not document:
                            order = {**body, **totals, "id": 101, "branch_id": 1, "version": 1, "status": "draft", "supplier_id": 2, "purchase_order_number": "RETRY-001", "created_by_id": 1, "pdf_storage_key": None}
                            order.update({f"supplier_{key}": suppliers[1].get(key) for key in ("name", "gstin", "pan", "phone", "email")})
                            order.update({f"supplier_{key}": value for key, value in party["address"].items() if key != "name"})
                            document.append(order)
                            fulfill(route, {"detail": "Save response interrupted"}, 503)
                        else:
                            assert posts[-1] == posts[0], "Uncertain creation must resolve the original key and payload"
                            fulfill(route, document[0], 201)
                    elif endpoint == "/purchase-orders/101" and route.request.method == "PATCH":
                        update = body.get("domestic_details", body.get("reagent_details"))
                        patches.append(update)
                        if update["supplier_id"] != 2:
                            fulfill(route, {"detail": "Supplier cannot change during editing"}, 400)
                        else:
                            document[0].update(update, version=document[0]["version"] + 1)
                            fulfill(route, document[0])
                    else: _mock_api(route)

                page.route("**/api/v1/**", handle)
                page.goto(f'{os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")}/{path}')
                page.get_by_label("Saved seller", exact=True).select_option("2")
                page.get_by_label("PO No.", exact=True).fill("RETRY-001")
                page.get_by_label("Material name" if path == "purchase-orders" else "Product name", exact=True).fill("Retained material")
                page.get_by_label("HSN/SAC", exact=True).fill("29181590")
                page.get_by_label("Rate", exact=True).fill("100.00")
                if path == "reagent-purchase-orders": page.get_by_label("Manufacturer", exact=True).select_option("5")
                label = "Purchase orders" if path == "purchase-orders" else "Reagent purchase orders"
                navigate(page, "Customers"); navigate(page, label)
                expect(page.get_by_label("Saved seller", exact=True)).to_have_value("2")
                expect(page.get_by_label("PO No.", exact=True)).to_have_value("RETRY-001")
                expect(page.get_by_role("textbox", name="Material name" if path == "purchase-orders" else "Product name", exact=True)).to_have_value("Retained material")
                assert not posts, "Unsaved navigation must not start a creation request"
                save = page.get_by_role("button", name="Save purchase order" if path == "purchase-orders" else "Save reagent purchase order", exact=True)
                save.click()
                expect(page.get_by_role("alert").filter(has_text="Save response interrupted")).to_be_visible()
                navigate(page, "Customers"); navigate(page, label)
                expect(page.get_by_role("alert").filter(has_text="Save response interrupted")).to_be_visible()
                expect(page.get_by_label("Saved seller", exact=True)).to_have_value("2")
                page.get_by_label("Saved seller", exact=True).select_option("1")
                page.get_by_label("Payment terms").fill("45 days retained")
                save.click()
                expect(page.get_by_label("Saved seller", exact=True)).to_have_value("2")
                expect(page.get_by_label("Saved seller", exact=True)).to_be_disabled()
                expect(page.get_by_role("region", name="Seller / Shipping Address")).to_contain_text("Original Seller")
                expect(page.get_by_label("Payment terms")).to_have_value("45 days retained")
                page.get_by_role("button", name="Save purchase order" if path == "purchase-orders" else "Save reagent PO changes", exact=True).click()
                expect(page.get_by_role("alert").filter(has_text="Supplier cannot change")).to_have_count(0)
                assert len(document) == 1 and len(posts) == 2 and posts[0] == posts[1]
                assert patches[-1]["supplier_id"] == 2 and document[0]["payment_terms"] == "45 days retained"
                page.close()
                print(f"{path}: lost-response seller recovery preserves other fields and resumes one saved order")
        finally:
            browser.close()


if __name__ == "__main__": main()
