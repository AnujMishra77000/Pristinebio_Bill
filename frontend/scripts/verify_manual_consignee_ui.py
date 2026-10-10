"""Verify manual sales entry exposes an editable consignee section.

Run with a Next.js server on FRONTEND_BASE_URL, for example:
FRONTEND_BASE_URL=http://127.0.0.1:3100 ../backend/.venv/bin/python scripts/verify_manual_consignee_ui.py
"""

from __future__ import annotations

import json
import os

from playwright.sync_api import Route, expect, sync_playwright


BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3100")


def _json(route: Route, payload: object, status: int = 200) -> None:
    route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))


def _mock_api(route: Route) -> None:
    url = route.request.url
    if url.endswith("/api/v1/auth/me"):
        _json(route, {"id": 1, "email": "admin@example.com", "full_name": "Admin User", "role": "admin", "branch_ids": [], "is_active": True, "password_change_required": False, "mfa_enabled": True, "mfa_required": True, "mfa_verified": True})
    elif url.endswith("/api/v1/auth/csrf"):
        _json(route, {"csrf_token": "test-csrf"})
    elif url.endswith("/api/v1/companies/profile"):
        _json(route, {"company": {"id": 1, "legal_name": "Pristine Biopharma", "trade_name": None, "pan": None, "registered_address": None, "logo_data_uri": None, "is_active": True}, "seller_profile": {"id": 1, "company_id": 1, "name": "Pristine Biopharma", "gstin": "36AAAAA0000A1Z5", "address_line1": "Seller Street", "address_line2": None, "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001", "is_active": True}})
    elif url.split("?", 1)[0].endswith("/api/v1/customers"):
        _json(route, [{"id": 7, "branch_id": 1, "name": "Saved Buyer", "gstin": "36AAAAA0000A1Z5", "pan": "AAAAA0000A", "email": "buyer@example.com", "phone": "9000000000", "billing_address": {"name": "Saved Buyer", "address_line1": "Buyer Address", "address_line2": "Buyer Address 2", "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001"}, "shipping_address": None, "is_active": True}])
    elif url.endswith("/api/v1/products"):
        _json(route, [{"id": 8, "branch_id": 1, "name": "Sodium Citrate", "description": "Sodium Citrate BP", "hsn_sac": "29181590", "unit": "KG", "base_rate": "30.00", "gst_rate": "18.00", "cess_rate": "0.00", "is_active": True}])
    elif route.request.method == "POST" and url.endswith("/api/v1/invoices/preview"):
        _json(route, {"lines": [], "taxable_value": "0.00", "cgst_amount": "0.00", "sgst_amount": "0.00", "igst_amount": "0.00", "cess_amount": "0.00", "unrounded_total": "0.00", "round_off": "0.00", "final_total": "0.00", "amount_in_words": "Rupees Zero Only"})
    elif url.endswith("/api/v1/invoices"):
        _json(route, [])
    else:
        route.continue_()


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        captured_invoice_payload: dict[str, object] = {}
        def mock_api(route: Route) -> None:
            if route.request.method == "POST" and route.request.url.endswith("/api/v1/invoices"):
                captured_invoice_payload.update(json.loads(route.request.post_data or "{}"))
                _json(route, {"id": 1, "status": "draft", "invoice_number": None, "final_total": "0.00"})
                return
            _mock_api(route)

        page.route("**/api/v1/**", mock_api)
        page.goto(f"{BASE_URL}/invoices")

        toggle = page.get_by_role("checkbox", name="Consignee same as buyer")
        expect(toggle).to_be_visible()
        expect(toggle).to_be_checked()
        toggle.uncheck()
        expect(page.get_by_role("heading", name="Consignee details")).to_be_visible()
        expect(page.get_by_label("Consignee name", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee GSTIN", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee PAN", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee Phone", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee Email", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee Address line 1", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee Address line 2", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee City", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee State", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee State code", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee Postal code", exact=True)).to_be_editable()

        page.get_by_label("Buyer/vendor name").fill("Buyer Labs")
        page.get_by_label("Address line 1", exact=True).fill("Buyer Street")
        page.get_by_label("City", exact=True).fill("Hyderabad")
        page.get_by_label("State", exact=True).fill("Telangana")
        page.get_by_label("Postal code", exact=True).fill("500001")
        page.get_by_label("Consignee name", exact=True).fill("Delivery Warehouse")
        page.get_by_label("Consignee GSTIN", exact=True).fill("36BBBBB0000B1Z6")
        page.get_by_label("Consignee PAN", exact=True).fill("BBBBB0000B")
        page.get_by_label("Consignee Phone", exact=True).fill("9876543210")
        page.get_by_label("Consignee Email", exact=True).fill("warehouse@example.com")
        page.get_by_label("Consignee Address line 1", exact=True).fill("Warehouse Road")
        page.get_by_label("Consignee Address line 2", exact=True).fill("Gate 2")
        page.get_by_label("Consignee City", exact=True).fill("Secunderabad")
        page.get_by_label("Consignee State", exact=True).fill("Telangana")
        page.get_by_label("Consignee State code", exact=True).fill("36")
        page.get_by_label("Consignee Postal code", exact=True).fill("500003")
        page.get_by_label("Product name").fill("Sodium Citrate")
        page.get_by_label("HSN/SAC").fill("29181590")
        page.get_by_label("Rate", exact=True).fill("30.00")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/api/v1/invoices")):
            page.get_by_role("button", name="Save sales invoice draft").click()
        expect(page.get_by_text("Sales invoice draft saved.")).to_be_visible()
        assert captured_invoice_payload["consignee"]["name"] == "Delivery Warehouse"
        assert captured_invoice_payload["consignee"]["billing_address"]["address_line1"] == "Warehouse Road"
        assert captured_invoice_payload["consignee"]["shipping_address"]["city"] == "Secunderabad"

        page.get_by_role("button", name="Use saved data").click()
        page.get_by_role("combobox", name="Saved buyer", exact=True).select_option("7")
        expect(page.get_by_label("Consignee name", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee GSTIN", exact=True)).to_have_value("36AAAAA0000A1Z5")
        expect(page.get_by_role("textbox", name="Consignee Address line 1", exact=True)).to_have_value("Buyer Address")
        expect(page.get_by_label("Consignee City", exact=True)).to_have_value("Hyderabad")
        assert page.get_by_label("Consignee GSTIN", exact=True).is_editable() is False
        assert page.get_by_role("textbox", name="Consignee Address line 1", exact=True).is_editable() is False
        expect(page.get_by_label("Consignee PAN", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee Phone", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee Email", exact=True)).to_be_editable()
        expect(page.get_by_label("Consignee", exact=True)).to_have_count(0)
        page.get_by_label("Consignee name", exact=True).fill("Saved Delivery Warehouse")
        page.get_by_label("Consignee PAN", exact=True).fill("BBBBB0000B")
        page.get_by_label("Consignee Phone", exact=True).fill("9111111111")
        page.get_by_label("Consignee Email", exact=True).fill("delivery@example.com")
        page.get_by_role("combobox").nth(1).select_option("8")
        with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/api/v1/invoices")):
            page.get_by_role("button", name="Save sales invoice draft").click()
        expect(page.get_by_text("Sales invoice draft saved.")).to_be_visible()
        assert captured_invoice_payload["buyer_customer_id"] == 7
        assert "consignee_customer_id" not in captured_invoice_payload
        assert captured_invoice_payload["consignee"]["name"] == "Saved Delivery Warehouse"
        assert captured_invoice_payload["consignee"]["gstin"] == "36AAAAA0000A1Z5"
        assert captured_invoice_payload["consignee"]["billing_address"]["address_line1"] == "Buyer Address"
        browser.close()


if __name__ == "__main__":
    main()
