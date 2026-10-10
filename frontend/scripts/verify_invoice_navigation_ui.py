"""Sales/Reagent route retention checks against real UI with isolated API fixtures."""
import json
import os
import traceback
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
from verify_invoice_financial_year_ui import _mock_api
from verify_reagent_purchase_order_ui import address, party, totals
from billing_test_pdf import blank_a4_pdf

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")
KINDS = (("invoices", "Sales invoices", "sales", "Sales bills"),
         ("reagent-bills", "Reagent bills", "reagent", "Reagent bills"))


def navigate(page, label):
    page.get_by_role("button", name="Explore", exact=True).click()
    link = page.get_by_role("dialog", name="Explore features").get_by_role("link", name=label, exact=True)
    destination = link.get_attribute("href")
    link.click()
    expect(page).to_have_url(f"{BASE_URL}{destination}")
    if label in ("Sales invoices", "Reagent bills"):
        expect(page.get_by_role("heading", name="Sales invoice entry" if label == "Sales invoices" else "Reagent bill entry", exact=True)).to_be_visible()


def snapshot(page):
    return page.locator("form[data-bill-entry] input, form[data-bill-entry] textarea, form[data-bill-entry] select").evaluate_all(
        "nodes => nodes.map(node => [node.type, node.value, node.type === 'checkbox' ? node.checked : null])")


def assert_snapshot(page, expected):
    # Controlled selects temporarily have no matching option while masters reload.
    page.wait_for_function("""expected => JSON.stringify(Array.from(document.querySelectorAll('form[data-bill-entry] input, form[data-bill-entry] textarea, form[data-bill-entry] select'),
        node => [node.type, node.value, node.type === 'checkbox' ? node.checked : null])) === JSON.stringify(expected)""", arg=expected, timeout=5000)


def fill_manual(page, kind):
    for label, value in (("Buyer/vendor name", f"Retained {kind} buyer"), ("Address line 1", "Entered street\nDifferent from saved address"),
                         ("City", "Hyderabad"), ("State", "Telangana"), ("State code", "36"), ("Postal code", "500001"),
                         ("Phone", "9000000000"), ("PAN", "ABCDE1234F"), ("Invoice No.", f"{kind}-017"),
                         ("Invoice date", "2026-10-06"), ("Delivery note date", "2026-10-07"),
                         ("Place of supply state code", "27"), ("Customer PO number", "CUSTOMER-PO-18"),
                         ("Payment terms", "45 days\nAfter delivery"), ("Dispatched through", "Courier"),
                         ("Vehicle number", "TS09AB1234"), ("LR/Docket number", "LR-123"), ("Freight charges", "10.00")):
        (page.get_by_role("textbox", name=label, exact=True) if label == "Payment terms" else page.get_by_label(label, exact=True)).fill(value)
    page.get_by_label("Consignee same as buyer", exact=True).uncheck()
    for label, value in (("Consignee name", "Separate consignee"), ("Consignee Address line 1", "Separate delivery street"),
                         ("Consignee City", "Mumbai"), ("Consignee State", "Maharashtra"), ("Consignee State code", "27"),
                         ("Consignee Postal code", "400001"), ("Consignee Phone", "9111111111")):
        page.get_by_label(label, exact=True).fill(value)
    page.get_by_role("button", name="Add line", exact=True).click()
    for index in range(2):
        page.get_by_role("textbox", name="Product name", exact=True).nth(index).fill(f"{kind} product {index}")
        page.get_by_label("Quantity", exact=True).nth(index).fill("12.345")
        page.get_by_label("HSN/SAC", exact=True).nth(index).fill("29181590")
        page.get_by_label("Rate", exact=True).nth(index).fill("100.1234")
        page.get_by_role("textbox", name="Item Description" if kind == "reagent" else "Description", exact=True).nth(index).fill("Long entered description\nSecond line")
        if kind == "reagent":
            page.get_by_role("combobox", name="MFG / Manufacturer", exact=True).nth(index).select_option("5")
            page.get_by_label("Pack/Size", exact=True).nth(index).fill("500 g")
            page.get_by_label("MFG Product Code / Part No.", exact=True).nth(index).fill(f"ARTICLE-{index}")


def main():
    failures = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chromium")
        for path, link_label, kind, register_title in KINDS:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(5000)
            unexpected = []
            errors, attempts, patches, documents, keys, pending = [], [], [], [], {}, []
            state = {"lost": True, "delay_patch": False, "user_id": 1, "authenticated": True, "logout_failure": True, "customer_failure": False}
            user = {"id": 1, "email": "admin@example.test", "full_name": "Admin User", "role": "admin", "branch_ids": [],
                    "is_active": True, "password_change_required": False, "mfa_required": False, "mfa_enabled": False, "mfa_verified": True}
            page.on("pageerror", lambda error: errors.append(str(error)))

            def fulfill(route, value, status=200):
                route.fulfill(status=status, content_type="application/json", body=json.dumps(value))

            def handle(route):
                api_path = urlparse(route.request.url).path.removeprefix("/api/v1")
                method = route.request.method
                if api_path == "/auth/me":
                    fulfill(route, {**user, "id": state["user_id"]} if state["authenticated"] else {"detail": "Signed out"}, 200 if state["authenticated"] else 401)
                elif api_path == "/auth/login":
                    state["authenticated"] = True
                    fulfill(route, {"user": {**user, "id": state["user_id"]}})
                elif api_path == "/auth/logout":
                    if state["logout_failure"]:
                        state["logout_failure"] = False
                        fulfill(route, {"detail": "Logout temporarily unavailable"}, 503)
                    else:
                        state["authenticated"] = False
                        fulfill(route, {"detail": "Logged out"})
                elif api_path == "/suppliers": fulfill(route, [{**party, "is_default": True}])
                elif api_path in ("/branches", "/purchasers"): fulfill(route, [])
                elif api_path == "/manufacturers": fulfill(route, [{"id": 5, "branch_id": 1, "name": "Merck", "code": "MRK", "is_active": True}])
                elif api_path == "/invoices/preview": fulfill(route, {**totals, "lines": []})
                elif api_path == "/invoices/register": fulfill(route, {"items": [], "total": 0, "page": 1, "page_size": 10})
                elif api_path == "/dashboard": fulfill(route, {"sales_invoice_count": 0, "reagent_invoice_count": 0, "domestic_oils_purchase_order_count": 0, "reagent_purchase_order_count": 0})
                elif api_path == "/customers":
                    fulfill(route, {"detail": "Customer lookup temporarily unavailable"} if state["customer_failure"] else [{**party, "billing_address": address, "shipping_address": address}], 503 if state["customer_failure"] else 200)
                elif api_path == "/products": fulfill(route, [{"id": 7, "branch_id": 1, "name": "Saved product", "description": "Saved description", "hsn_sac": "29181590", "unit": "kg", "base_rate": "100.00", "gst_rate": "5.00", "cess_rate": "0.00", "is_active": True}])
                elif api_path == "/invoices" and method == "POST":
                    key, body = route.request.headers["idempotency-key"], route.request.post_data_json
                    attempts.append((key, body))
                    if key in keys:
                        assert keys[key]["body"] == body, "Retry must use original key AND payload"
                        fulfill(route, keys[key]["document"], 201)
                    else:
                        document = {**body, **totals, "id": 101, "branch_id": 1, "version": 1, "status": "draft", "invoice_number": f"PBPL/2026-27/{kind.upper()}-017", "created_by_id": 1, "pdf_storage_key": None}
                        documents.append(document); keys[key] = {"body": body, "document": document}
                        if state["lost"]:
                            state["lost"] = False
                            fulfill(route, {"detail": "Creation response lost after commit"}, 503)
                        else: fulfill(route, document, 201)
                elif api_path == "/invoices/101" and method == "PATCH":
                    body = route.request.post_data_json
                    patches.append(body)
                    assert body["expected_version"] == documents[0]["version"]
                    if state["delay_patch"]:
                        state["delay_patch"] = False; pending.append((route, body))
                    else:
                        documents[0].update(body); documents[0]["version"] += 1
                        fulfill(route, documents[0])
                elif api_path == "/invoices/101/preview-pdf":
                    assert route.request.post_data_json["expected_version"] == documents[0]["version"]
                    route.fulfill(status=200, content_type="application/pdf", body=blank_a4_pdf())
                elif api_path in ("/auth/csrf", "/companies/profile"):
                    _mock_api(route)
                else:
                    unexpected.append((route.request.method, api_path))
                    route.abort()

            page.route("**/api/v1/**", handle)
            try:
                page.goto(f"{BASE_URL}/{path}")
                buyer = page.get_by_label("Buyer/vendor name", exact=True)
                expect(buyer).to_be_visible()
                fill_manual(page, kind)
                expect(page.get_by_label("Supplier", exact=True)).to_have_value("1")
                before = snapshot(page)
                navigate(page, "Customers")
                navigate(page, link_label)
                expect(buyer).to_have_value(f"Retained {kind} buyer")
                expect(page.get_by_label("Invoice No.", exact=True)).to_have_value(f"{kind.upper()}-017")
                assert_snapshot(page, before)
                button = page.locator("#workspace-content header").get_by_role("link", name=link_label, exact=True)
                expect(button).to_have_attribute("href", f"/bill-registers/{kind}")
                button.click()
                expect(page.get_by_role("heading", name=register_title, exact=True)).to_be_visible()
                navigate(page, link_label)
                expect(buyer).to_have_value(f"Retained {kind} buyer")
                assert_snapshot(page, before)
                panel = page.get_by_role("region", name="Bill submission", exact=True)
                preview = panel.get_by_role("button", name="Preview", exact=True)
                preview.click()
                expect(panel.get_by_role("alert")).to_contain_text("Creation response lost")
                navigate(page, "Customers"); navigate(page, link_label)
                expect(buyer).to_have_value(f"Retained {kind} buyer")
                page.get_by_role("textbox", name="Payment terms", exact=True).fill("60 days")
                preview.click()
                expect(panel.locator("iframe")).to_have_count(1)
                assert len(documents) == 1 and len(attempts) == 2 and attempts[0] == attempts[1], "Uncertain creation did not replay one exact intent"
                assert len(patches) == 1 and documents[0]["payment_terms"] == "60 days", "Changed input must PATCH the replayed draft"
                navigate(page, "Customers"); navigate(page, link_label)
                expect(panel.locator("iframe")).to_have_count(0)
                expect(panel.get_by_role("button", name="Confirm", exact=True)).to_be_disabled()
                expect(panel.get_by_role("button", name="Edit", exact=True)).to_be_enabled()
                expect(buyer).to_be_editable()
                preview.click()
                expect(panel.locator("iframe")).to_have_count(1)
                assert len(patches) == 1, "Returning to saved draft must not resave identical data"
                panel.get_by_role("button", name="Edit", exact=True).click()
                page.get_by_role("textbox", name="Payment terms", exact=True).fill("75 days")
                state["delay_patch"] = True
                with page.expect_request(lambda request: request.method == "PATCH" and request.url.endswith("/invoices/101")):
                    preview.click()
                navigate(page, "Customers"); navigate(page, link_label)
                expect(preview).to_be_disabled()
                assert pending, "Save must still be in flight"
                route, body = pending.pop()
                documents[0].update(body); documents[0]["version"] += 1
                fulfill(route, documents[0])
                expect(preview).to_be_enabled()
                expect(page.get_by_role("textbox", name="Payment terms", exact=True)).to_have_value("75 days")
                preview.click()
                expect(panel.locator("iframe")).to_have_count(1)
                assert len(documents) == 1 and len(attempts) == 2 and len(patches) == 2, "In-flight navigation issued another save"
                panel.get_by_role("button", name="Edit", exact=True).click()

                # A master refresh failure must not clear transaction consignee data.
                page.get_by_role("button", name="Use saved data", exact=True).click()
                page.locator("select:not(#invoice-supplier-choice)").filter(has=page.locator('option[value="1"]', has_text="Research Company")).select_option("1")
                for index in range(2):
                    page.get_by_role("combobox", name="Product", exact=True).nth(index).select_option("7")
                page.get_by_label("Consignee name", exact=True).fill("Retained on master failure")
                page.get_by_label("Consignee Phone", exact=True).fill("9333333333")
                page.get_by_role("button", name=f"Save {'reagent bill' if kind == 'reagent' else 'sales invoice'} draft", exact=True).click()
                expect(panel.get_by_role("status")).to_contain_text("Draft saved")
                navigate(page, other_label := ("Reagent bills" if kind == "sales" else "Sales invoices"))
                state["customer_failure"] = True
                navigate(page, link_label)
                expect(page.get_by_role("alert").filter(has_text="Customer lookup temporarily unavailable")).to_be_visible()
                page.get_by_role("textbox", name="Payment terms", exact=True).fill("85 days")
                page.get_by_role("button", name=f"Save {'reagent bill' if kind == 'reagent' else 'sales invoice'} draft", exact=True).click()
                expect(panel.get_by_role("status")).to_contain_text("Draft saved")
                assert patches[-1]["consignee"]["name"] == "Retained on master failure"
                assert patches[-1]["consignee"]["phone"] == "9333333333"
                state["customer_failure"] = False
                navigate(page, other_label)
                navigate(page, link_label)
                expect(page.get_by_label("Consignee name", exact=True)).to_have_value("Retained on master failure")

                # Independent kind survives Start new on this one.
                navigate(page, other_label)
                page.get_by_label("Buyer/vendor name", exact=True).fill("Other kind retained")
                navigate(page, link_label)
                panel.get_by_role("button", name="Start new bill", exact=True).click()
                expect(buyer).to_have_value("")
                navigate(page, other_label)
                expect(page.get_by_label("Buyer/vendor name", exact=True)).to_have_value("Other kind retained")
                navigate(page, link_label)
                page.get_by_role("button", name="Use saved data", exact=True).click()
                page.locator("select:not(#invoice-supplier-choice)").filter(has=page.locator('option[value="1"]', has_text="Research Company")).select_option("1")
                page.get_by_label("Consignee name", exact=True).fill("Saved buyer, manual consignee")
                page.get_by_label("Consignee Phone", exact=True).fill("9222222222")
                page.get_by_label("Place of supply state code", exact=True).fill("27")
                saved = snapshot(page)
                navigate(page, "Customers"); navigate(page, link_label)
                expect(page.get_by_label("Consignee name", exact=True)).to_have_value("Saved buyer, manual consignee")
                assert_snapshot(page, saved)
                page.set_viewport_size({"width": 390, "height": 844})
                expect(page.locator("#workspace-content header").get_by_role("link", name=link_label, exact=True)).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.set_viewport_size({"width": 1440, "height": 1000})

                # Failed logout retains work; successful logout off the entry page purges both kinds.
                navigate(page, "Customers")
                page.get_by_role("button", name="Log out", exact=True).click()
                expect(page.get_by_role("alert").filter(has_text="Logout temporarily unavailable")).to_be_visible()
                navigate(page, link_label)
                expect(page.get_by_label("Consignee name", exact=True)).to_have_value("Saved buyer, manual consignee")
                navigate(page, "Customers")
                page.get_by_role("button", name="Log out", exact=True).click()
                login = page.get_by_role("link", name="Go to login →", exact=True)
                expect(login).to_be_visible(); login.click()
                page.get_by_label("Email", exact=True).fill("admin@example.test")
                page.get_by_label("Password", exact=True).fill("Test!123")
                page.locator("form").get_by_role("button", name="Sign in", exact=True).click()
                # Auth completion lands on dashboard; avoid its unrelated API calls by
                # immediately using the entry navigation once the app shell is shown.
                navigate(page, link_label)
                expect(buyer).to_have_value("")
                navigate(page, other_label)
                expect(page.get_by_label("Buyer/vendor name", exact=True)).to_have_value("")
                page.get_by_label("Buyer/vendor name", exact=True).fill("Refresh must clear")
                page.reload()
                expect(page.get_by_label("Buyer/vendor name", exact=True)).to_have_value("")
                assert not page.evaluate("JSON.stringify({...localStorage, ...sessionStorage}).includes('Retained')")
                assert not unexpected, unexpected
                assert not errors, errors
            except Exception as error:
                failures.append(f"{kind}: {error}\n{traceback.format_exc()}")
            finally:
                page.close()
        browser.close()
    if failures:
        raise AssertionError("\n".join(failures))
    print("Sales/Reagent: register links, all fields/dynamic lines, independent sessions, saved draft/version, uncertain/in-flight saves, fresh review, saved consignee, mobile, reset/logout and refresh checks passed.")


if __name__ == "__main__":
    main()
