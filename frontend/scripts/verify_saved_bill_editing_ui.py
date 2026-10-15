"""Register → existing draft → versioned save/preview/confirm, all four types.

All API traffic is intercepted; no client data or live backend is used.
"""
from copy import deepcopy
import json
import os
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright
from billing_test_pdf import blank_a4_pdf
from verify_invoice_financial_year_ui import _mock_api

BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://127.0.0.1:3000")
CASES = [("sales", "invoices", "sales", "invoices", "Sales invoice entry"),
         ("reagent", "invoices", "reagent", "reagent-bills", "Reagent bill entry"),
         ("purchase", "purchase-orders", "domestic_oils", "purchase-orders", "Purchase order entry"),
         ("reagent-purchase", "purchase-orders", "reagent", "reagent-purchase-orders", "Reagent purchase order")]


def fixture(collection, document_type):
    totals = {"taxable_value": "100.00", "cgst_amount": "9.00", "sgst_amount": "9.00", "igst_amount": "0.00", "cess_amount": "0.00",
              "unrounded_total": "118.00", "round_off": "0.00", "final_total": "118.00", "amount_in_words": "Rupees One Hundred Eighteen Only"}
    line = {"id": 10, "product_id": 8, "sort_order": 1, "product_name": "Snapshot Material", "description": "Snapshot description",
            "manufacturer_id": 5, "manufacturer_name": "Merck", "manufacturer_code": "MRK", "manufacturer_product_code": "ART-18", "part_no": "ART-18", "pack_size": "500 g",
            "hsn_sac": "29181590", "quantity": "1.000", "unit": "kg", "rate": "100.0000", "other_charge": "0.00", "discount_amount": "0.00", "discount_percent": "0.00",
            "taxable_value": "100.00", "gst_rate": "18.00", "cess_rate": "0.00", "cgst_amount": "9.00", "sgst_amount": "9.00", "igst_amount": "0.00", "cess_amount": "0.00", "line_total": "118.00"}
    # Invoice APIs expose manufacturer code snapshots, not a manufacturer ID.
    if collection == "invoices": line.pop("manufacturer_id")
    document = {**totals, "id": 101, "document_type": document_type, "branch_id": 1, "version": 5, "status": "draft", "created_by_id": 1,
                "supplier_id": 1, "submitted_by_id": None, "submitted_revision": None, "approved_revision": None, "pdf_storage_key": None,
                "transport_mode": "ROAD", "vehicle_number": "TS09AB1234", "vehicle_type": "Truck", "lr_number": "LR-18", "lr_date": "2026-10-05",
                "expected_delivery_date": "2026-10-15", "payment_terms": "Snapshot terms", "place_of_supply_state_code": "36", "delivery_note_date": "2026-10-05",
                "freight_charges": "0.00", "packing_charges": "0.00", "other_charges": "0.00", "discount_amount": "0.00", "lines": [line]}
    for prefix, name, street in (("buyer", "Snapshot Buyer", "Saved Billing Street"), ("consignee", "Snapshot Warehouse", "Saved Shipping Street"), ("supplier", "Snapshot Seller", "Saved Seller Street")):
        document.update({f"{prefix}_{key}": value for key, value in {"name": name, "gstin": "36ABCDE1234F1Z5", "pan": "ABCDE1234F", "phone": "9111111111", "email": "snapshot@example.com",
                         "address_line1": street, "address_line2": "Gate 2", "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001"}.items()})
    document.update(invoice_number="PBPL/2026-27/EDIT-101", invoice_date="2026-10-05", buyer_customer_id=7, consignee_customer_id=None, po_number="BUYER-PO-18",
                    purchase_order_number="PO-EDIT-101", order_date="2026-10-05", purchaser_id=None, purchaser_name=None, po_reference_number="BUYER-PO-18", po_reference_date="2026-10-04", consignee=None)
    if collection == "purchase-orders":
        for key in ["invoice_number", "invoice_date", *[key for key in document if key.startswith("buyer_")]]:
            document.pop(key, None)
    return document


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for kind, collection, document_type, entry, heading in CASES:
            page = browser.new_page()
            document = fixture(collection, document_type)
            patches, creates, unexpected, errors = [], [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            address = {"name": "Current master", "address_line1": "Changed master street", "address_line2": None, "city": "Hyderabad", "state": "Telangana", "state_code": "36", "postal_code": "500001"}
            supplier = {"id": 1, "branch_id": 1, "name": "Current seller master", "gstin": "36ABCDE1234F1Z5", "pan": "ABCDE1234F", "phone": "9000000000", "email": "master@example.com", "address": address, "is_active": True, "is_default": True}

            def fulfill(route, payload, status=200):
                route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

            def handle(route):
                path = urlsplit(route.request.url).path.removeprefix("/api/v1")
                method = route.request.method
                if path in ("/auth/me", "/auth/csrf", "/companies/profile"): _mock_api(route)
                elif path in ("/suppliers",): fulfill(route, [supplier])
                elif path == "/suppliers/1": fulfill(route, supplier)
                elif path == "/customers": fulfill(route, [{**supplier, "id": 7, "billing_address": address, "shipping_address": address}])
                elif path == "/manufacturers": fulfill(route, [{"id": 5, "branch_id": 1, "name": "Merck", "code": "MRK", "is_active": True}])
                elif path == "/products": fulfill(route, [{"id": 8, "branch_id": 1, "name": "Changed master product", "description": "Changed description", "hsn_sac": "29181590", "unit": "kg", "base_rate": "900.00", "gst_rate": "18.00", "cess_rate": "0.00", "is_active": True}])
                elif path == f"/{collection}/register":
                    approved = {**document, "id": 102, "status": "pdf_generated" if collection == "invoices" else "approved",
                                **({"invoice_number": "PBPL/2026-27/FINAL-102"} if collection == "invoices" else {"purchase_order_number": "PO-FINAL-102"})}
                    fulfill(route, {"items": [document, approved], "total": 2, "page": 1, "page_size": 10})
                elif path == f"/{collection}/101" and method == "GET": fulfill(route, document)
                elif path == f"/{collection}/101" and method == "PATCH":
                    body = route.request.post_data_json
                    assert body["expected_version"] == document["version"], body
                    patches.append(body)
                    document["version"] += 1
                    details = body.get("domestic_details") or body.get("reagent_details") or body
                    document["lines"][0]["quantity"] = details["lines"][0]["quantity"]
                    document["final_total"] = "236.00"
                    fulfill(route, document)
                elif path == f"/{collection}" and method == "POST":
                    creates.append(route.request.post_data_json); fulfill(route, {"detail": "Editor must not create a second document"}, 500)
                elif path.endswith("/preview"):
                    fulfill(route, {**document, "lines": []})
                elif path == f"/{collection}/101/preview-pdf":
                    assert route.request.post_data_json["expected_version"] == document["version"]
                    route.fulfill(status=200, content_type="application/pdf", body=blank_a4_pdf())
                elif path == f"/{collection}/101/submit":
                    assert route.request.post_data_json["expected_version"] == document["version"]
                    document["submitted_revision"] = document["version"]; document["version"] += 1; document["status"] = "pending_approval"
                    fulfill(route, document)
                elif path == f"/{collection}/101/approve":
                    document["version"] += 1; document["status"] = "approved"; document["approved_revision"] = document["submitted_revision"]
                    fulfill(route, document)
                elif path == f"/{collection}/101/generate-pdf":
                    document["pdf_storage_key"] = "isolated.pdf"; document["status"] = "pdf_generated" if collection == "invoices" else "approved"
                    fulfill(route, document)
                elif path == f"/{collection}/101/pdf": route.fulfill(status=200, content_type="application/pdf", body=blank_a4_pdf())
                else: unexpected.append((method, path)); route.abort()

            page.route("**/api/v1/**", handle)
            page.goto(f"{BASE_URL}/bill-registers/{kind}")
            expect(page.get_by_role("link", name="Edit bill PBPL/2026-27/FINAL-102" if collection == "invoices" else "Edit bill PO-FINAL-102", exact=True)).to_have_attribute("href", f"/{entry}?{'invoice' if collection == 'invoices' else 'order'}=102&correction=1")
            edit = page.get_by_role("link", name="Edit bill PBPL/2026-27/EDIT-101" if collection == "invoices" else "Edit bill PO-EDIT-101", exact=True)
            expect(edit).to_be_visible()
            expect(edit).to_have_attribute("href", f"/{entry}?{'invoice' if collection == 'invoices' else 'order'}=101")
            edit.click()
            expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
            expect(page.get_by_label("Quantity", exact=True)).to_have_value("1.000")
            expect(page.get_by_label("Rate", exact=True)).to_have_value("100.0000")
            if collection == "invoices":
                expect(page.get_by_label("Buyer/vendor name", exact=True)).to_have_value("Snapshot Buyer")
                expect(page.get_by_label("Consignee name", exact=True)).to_have_value("Snapshot Warehouse")
                expect(page.get_by_role("textbox", name="Address line 1", exact=True)).to_have_value("Saved Billing Street")
                expect(page.get_by_role("textbox", name="Consignee Address line 1", exact=True)).to_have_value("Saved Shipping Street")
                expect(page.get_by_label("Invoice No.", exact=True)).to_have_value("EDIT-101")
            else:
                expect(page.get_by_label("PO No.", exact=True)).to_have_value("PO-EDIT-101")
                expect(page.get_by_text("Snapshot Seller", exact=True).first).to_be_visible()
            if document_type == "reagent": expect(page.get_by_role("combobox", name="MFG / Manufacturer" if collection == "invoices" else "Manufacturer", exact=True)).to_have_value("5")
            page.get_by_label("Quantity", exact=True).fill("2.000")
            panel = page.get_by_role("region", name="Bill submission", exact=True)
            panel.get_by_role("button", name="Preview", exact=True).click()
            expect(panel.locator("iframe")).to_have_count(1)
            assert len(patches) == 1 and not creates
            edited = patches[0].get("domestic_details") or patches[0].get("reagent_details") or patches[0]
            assert edited["lines"][0]["quantity"] == "2.000"
            assert edited["lines"][0]["rate"] == "100.0000"
            assert edited["lines"][0]["description"] == "Snapshot description"
            assert edited["lines"][0]["product_name"] == "Snapshot Material"
            assert edited["lines"][0]["product_id"] == 8
            panel.get_by_role("button", name="Confirm", exact=True).click()
            expect(panel.get_by_role("button", name="Download", exact=True)).to_be_enabled()
            expect(panel.get_by_role("button", name="Print", exact=True)).to_be_enabled()
            expect(page.get_by_label("Quantity", exact=True)).to_be_disabled()
            assert document["id"] == 101 and not creates
            assert not unexpected, unexpected
            assert not errors, errors
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            if collection == "invoices":
                panel.get_by_role("button", name="Start new bill", exact=True).click()
                expect(page.get_by_label("Invoice No.", exact=True)).to_have_value("")
                assert "invoice=" not in page.url
            else:
                page.get_by_role("button", name="Start new bill" if document_type == "domestic_oils" else "Start new order", exact=True).click()
                expect(page.get_by_label("PO No.", exact=True)).to_have_value("")
                assert "order=" not in page.url
            page.close()
        browser.close()
    print("Passed: all four register Edit links, snapshot hydration, one versioned PATCH, preview, confirmation, read-only final state and responsive width")


if __name__ == "__main__": main()
