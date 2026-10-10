from sqlalchemy import func, select
import pytest

from app.models.master_records import Customer
from tests.test_customer_gstin_identity import _legacy_customer
from tests.test_master_records import customer_payload
from tests.test_financial_correctness import _customer, _invoice_payload


def test_register_deduplicates_normalized_gstin_before_limit_and_prefers_active(client, auth_headers, staff_user, branch, db_session):
    inactive = _legacy_customer(db_session, branch.id, "Old disabled buyer", "29abcde1234f1z5", active=False)
    active = _legacy_customer(db_session, branch.id, "Active buyer", " 29ABCDE1234F1Z5 ")
    duplicate = _legacy_customer(db_session, branch.id, "Historical duplicate", "29ABCDE1234F1Z5")
    disabled_only = _legacy_customer(db_session, branch.id, "Disabled only", "29FGHIJ1234K1Z5", active=False)
    _legacy_customer(db_session, branch.id, "Disabled duplicate", "29fghij1234k1z5", active=False)
    headers = auth_headers(staff_user)
    response = client.get("/api/v1/customers?register=true&limit=2", headers=headers)
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [active.id, disabled_only.id]
    second_page = client.get("/api/v1/customers?register=true&limit=1&offset=1", headers=headers)
    assert [row["id"] for row in second_page.json()] == [disabled_only.id]
    assert client.get(f"/api/v1/customers/{duplicate.id}", headers=headers).status_code == 200
    generic = client.get("/api/v1/customers", headers=headers).json()
    assert inactive.id in [row["id"] for row in generic]
    assert duplicate.id in [row["id"] for row in generic]
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 5


def test_register_keeps_unregistered_buyers_and_profile_authorization(client, auth_headers, staff_user, admin_user, branch, other_branch, db_session):
    first = _legacy_customer(db_session, branch.id, "Unregistered A", None)
    second = _legacy_customer(db_session, branch.id, "Unregistered B", "   ")
    local = _legacy_customer(db_session, branch.id, "Local buyer", "29ABCDE1234F1Z5")
    remote = _legacy_customer(db_session, other_branch.id, "Other profile buyer", "29ABCDE1234F1Z5")
    staff = auth_headers(staff_user)
    assert [row["id"] for row in client.get("/api/v1/customers?register=true", headers=staff).json()] == [first.id, second.id, local.id]
    assert client.get(f"/api/v1/customers?register=true&branch_id={other_branch.id}", headers=staff).status_code == 403
    assert [row["id"] for row in client.get("/api/v1/customers?register=true", headers=auth_headers(admin_user)).json()] == [first.id, second.id, local.id, remote.id]


def test_customer_edit_updates_same_id_and_can_clear_shipping_without_creating_customer(client, auth_headers, staff_user, branch, db_session):
    headers = auth_headers(staff_user)
    original = client.post("/api/v1/customers", headers=headers, json=customer_payload(branch.id)).json()
    assert original["shipping_address"] is not None
    billing = {**original["billing_address"], "address_line1": "Corrected billing street"}
    response = client.patch(f"/api/v1/customers/{original['id']}", headers=headers, json={
        "name": "Updated buyer", "phone": "9001234567", "email": "updated@example.com",
        "billing_address": billing, "shipping_address": None,
    })
    assert response.status_code == 200
    saved = response.json()
    assert saved["id"] == original["id"]
    assert saved["name"] == "Updated buyer"
    assert saved["billing_address"]["address_line1"] == "Corrected billing street"
    assert saved["shipping_address"] is None
    assert saved["phone"] == "9001234567"
    assert saved["email"] == "updated@example.com"
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 1


def test_customer_edit_omitted_addresses_preserve_values_and_collision_is_clear(client, auth_headers, staff_user, branch):
    headers = auth_headers(staff_user)
    first = client.post("/api/v1/customers", headers=headers, json=customer_payload(branch.id)).json()
    other_payload = customer_payload(branch.id, "Other buyer")
    other_payload["gstin"] = "29FGHIJ1234K1Z5"
    other = client.post("/api/v1/customers", headers=headers, json=other_payload).json()
    edited = client.patch(f"/api/v1/customers/{first['id']}", headers=headers, json={"phone": "9001111111"})
    assert edited.status_code == 200
    assert edited.json()["billing_address"] == first["billing_address"]
    assert edited.json()["shipping_address"] == first["shipping_address"]
    collision = client.patch(f"/api/v1/customers/{first['id']}", headers=headers, json={"gstin": other["gstin"]})
    assert collision.status_code == 409
    assert collision.json()["detail"]["field"] == "gstin"


def test_customer_edit_rejects_null_required_fields(client, auth_headers, staff_user, branch):
    headers = auth_headers(staff_user)
    customer = client.post("/api/v1/customers", headers=headers, json=customer_payload(branch.id)).json()
    for field in ("name", "billing_address", "branch_id", "is_active"):
        response = client.patch(f"/api/v1/customers/{customer['id']}", headers=headers, json={field: None})
        assert response.status_code == 422, (field, response.text)
        assert any(issue["loc"][-1] == field for issue in response.json()["detail"])


@pytest.mark.parametrize("document_type", ["sales", "reagent"])
def test_selected_buyer_snapshot_survives_master_edit_save_and_approval(client, auth_headers, staff_user, manager_user, branch, document_type):
    headers = auth_headers(staff_user)
    snapshot = _customer("Chosen buyer", "36ABCDE1234F1Z5", address_line1="Chosen transaction street")
    customer = client.post("/api/v1/customers", headers=headers, json={"branch_id": branch.id, **snapshot}).json()
    edited_master = client.patch(f"/api/v1/customers/{customer['id']}", headers=headers, json={
        "billing_address": {**customer["billing_address"], "address_line1": "Later master street"},
    })
    assert edited_master.status_code == 200
    payload = _invoice_payload(branch, buyer=snapshot)
    payload.update(buyer_customer_id=customer["id"], document_type=document_type)
    if document_type == "reagent":
        manufacturer = client.post("/api/v1/manufacturers", headers=headers, json={"branch_id": branch.id, "code": "MRK", "name": "Merck"}).json()
        payload["lines"][0]["manufacturer_id"] = manufacturer["id"]
    created = client.post("/api/v1/invoices", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    document = created.json()
    assert document["buyer_customer_id"] == customer["id"]
    assert document["buyer_address_line1"] == "Chosen transaction street"
    updated = client.patch(f"/api/v1/invoices/{document['id']}", headers=headers, json={
        "expected_version": document["version"], "buyer_customer_id": customer["id"], "buyer": snapshot, "payment_terms": "Retained revision",
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["buyer_customer_id"] == customer["id"]
    submitted = client.post(f"/api/v1/invoices/{document['id']}/submit", headers=headers)
    assert submitted.status_code == 200
    approved = client.post(f"/api/v1/invoices/{document['id']}/approve", headers=auth_headers(manager_user))
    assert approved.status_code == 200, approved.text
    assert approved.json()["buyer_address_line1"] == "Chosen transaction street"
    assert client.get(f"/api/v1/customers/{customer['id']}", headers=headers).json()["billing_address"]["address_line1"] == "Later master street"
