from datetime import UTC, datetime

import pytest

from app.models.invoice import Invoice
from app.models.master_records import Customer
from app.services.invoice_pdf import build_invoice_context, build_invoice_html
from tests.test_financial_correctness import _customer, _invoice_payload
from tests.test_master_records import customer_payload


@pytest.mark.parametrize("document_type", ["sales", "reagent"])
@pytest.mark.parametrize("address_choice", ["shipping", "billing", "no_shipping"])
def test_saved_address_choice_is_snapshotted_for_pdf_and_survives_master_edits(
    document_type, address_choice, client, auth_headers, staff_user, manager_user, branch, db_session,
):
    headers = auth_headers(staff_user)
    master_payload = customer_payload(branch.id, "Saved Buyer")
    if address_choice == "no_shipping":
        master_payload["shipping_address"] = None
    created_master = client.post("/api/v1/customers", headers=headers, json=master_payload)
    assert created_master.status_code == 201
    customer = created_master.json()
    address = customer["shipping_address"] if address_choice == "shipping" else customer["billing_address"]
    expected_street = "Shipping Street 2" if address_choice == "shipping" else "Billing Street 1"
    expected_city = "Mysuru" if address_choice == "shipping" else "Bengaluru"
    expected_postal_code = "570001" if address_choice == "shipping" else "560001"
    consignee = _customer("Entered Delivery Party", customer["gstin"])
    consignee.update(pan="FGHIJ1234K", phone="9111111111", email="delivery@example.com")
    consignee["billing_address"] = {**address, "name": "Entered Delivery Party"}
    consignee["shipping_address"] = {**address, "name": "Entered Delivery Party"}
    payload = _invoice_payload(branch)
    payload.pop("buyer")
    payload.update(buyer_customer_id=customer["id"], consignee=consignee, document_type=document_type,
                   place_of_supply_state_code="29")
    if document_type == "reagent":
        manufacturer = client.post("/api/v1/manufacturers", headers=headers, json={"branch_id": branch.id, "code": "SIG", "name": "Sigma"})
        assert manufacturer.status_code == 201
        payload["lines"][0]["manufacturer_id"] = manufacturer.json()["id"]
    preview = client.post("/api/v1/invoices/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    created = client.post("/api/v1/invoices", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    document = created.json()
    assert document["buyer_address_line1"] == "Billing Street 1"
    assert document["consignee_address_line1"] == expected_street
    assert document["consignee_city"] == expected_city
    assert document["consignee_postal_code"] == expected_postal_code
    assert document["consignee_name"] == "Entered Delivery Party"
    assert document["consignee_phone"] == "9111111111"
    assert document["consignee_email"] == "delivery@example.com"
    assert document["consignee_customer_id"] is None
    assert document["final_total"] == preview.json()["final_total"] == "118.00"
    assert document["igst_amount"] == "18.00"
    # Master edits must not silently change an already reviewed transaction.
    changed_address = {**customer["billing_address"], "address_line1": "New master street"}
    changed = client.patch(f"/api/v1/customers/{customer['id']}", headers=headers,
                           json={"billing_address": changed_address, "shipping_address": changed_address})
    assert changed.status_code == 200
    edited = client.patch(f"/api/v1/invoices/{document['id']}", headers=headers,
                          json={"expected_version": document["version"], "payment_terms": "45 days"})
    assert edited.status_code == 200
    assert client.post(f"/api/v1/invoices/{document['id']}/submit", headers=headers).status_code == 200
    approved = client.post(f"/api/v1/invoices/{document['id']}/approve", headers=auth_headers(manager_user))
    assert approved.status_code == 200, approved.text
    assert approved.json()["consignee_address_line1"] == expected_street
    assert approved.json()["buyer_address_line1"] == "Billing Street 1"
    assert approved.json()["final_total"] == "118.00"
    snapshot = db_session.get(Invoice, document["id"])
    context = build_invoice_context(snapshot, branch=branch, generated_at=datetime.now(UTC))
    assert context.buyer.address_lines[0] == "Billing Street 1"
    assert context.consignee.address_lines[0] == expected_street
    assert expected_city in " ".join(context.consignee.address_lines)
    assert expected_postal_code in " ".join(context.consignee.address_lines)
    assert context.consignee.name == "Entered Delivery Party"
    html = build_invoice_html(context)
    assert expected_street in html
    assert "New master street" not in html
    assert html.count("Entered Delivery Party") == 4
    if address_choice == "shipping":
        assert html.count("Shipping Street 2") == 4
    assert db_session.get(Customer, customer["id"]).billing_address_line1 == "New master street"
