from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select

from app.models.master_records import Customer
from tests.test_master_records import customer_payload
from tests.test_financial_correctness import _customer, _invoice_payload
from app.services.customer_identity import lock_customer_gstin


def _legacy_customer(db, branch_id, name, gstin, *, active=True):
    payload = customer_payload(branch_id, name)
    billing = payload.pop("billing_address")
    shipping = payload.pop("shipping_address")
    payload.update(gstin=gstin, is_active=active)
    row = Customer(**payload, **{f"billing_{key}": value for key, value in billing.items()},
                   **{f"shipping_{key}": value for key, value in shipping.items()})
    db.add(row)
    db.commit()
    return row


def test_customer_save_reuses_normalized_gstin_without_overwriting_master(client, auth_headers, staff_user, branch, db_session):
    headers = auth_headers(staff_user)
    first = client.post("/api/v1/customers", headers=headers, json=customer_payload(branch.id)).json()
    retry = customer_payload(branch.id, "Changed company name")
    retry["gstin"] = " 29abcde1234f1z5 "
    retry["billing_address"]["address_line1"] = "New transaction street"
    response = client.post("/api/v1/customers", headers=headers, json=retry)
    assert response.status_code == 200
    assert response.json()["id"] == first["id"]
    assert response.json()["name"] == first["name"]
    assert response.json()["billing_address"]["address_line1"] == "Billing Street 1"
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 1


def test_new_customer_gstin_is_uppercase(client, auth_headers, staff_user, branch):
    payload = customer_payload(branch.id)
    payload["gstin"] = " 29abcde1234f1z5 "
    response = client.post("/api/v1/customers", headers=auth_headers(staff_user), json=payload)
    assert response.status_code == 201
    assert response.json()["gstin"] == "29ABCDE1234F1Z5"


def test_billing_list_hides_legacy_duplicates_before_limit_preserves_history_and_no_gstin(client, auth_headers, staff_user, branch, other_branch, db_session):
    first = _legacy_customer(db_session, branch.id, "Primary buyer", "29ABCDE1234F1Z5")
    duplicate = _legacy_customer(db_session, branch.id, "Old warehouse", "29abcde1234f1z5")
    _legacy_customer(db_session, branch.id, "Inactive", "29FGHIJ1234K1Z5", active=False)
    second = _legacy_customer(db_session, branch.id, "Second buyer", "29KLMNO1234P1Z5")
    unregistered = [_legacy_customer(db_session, branch.id, name, None).id for name in ("Unregistered A", "Unregistered B")]
    _legacy_customer(db_session, other_branch.id, "Unauthorized buyer", "29UVWXY1234Z1Z5")
    headers = auth_headers(staff_user)
    limited = client.get("/api/v1/customers?billing=true&limit=2", headers=headers)
    assert [row["id"] for row in limited.json()] == [first.id, second.id]
    billing = client.get("/api/v1/customers?billing=true", headers=headers).json()
    assert [row["id"] for row in billing] == [first.id, second.id, *unregistered]
    assert duplicate.id in [row["id"] for row in client.get("/api/v1/customers", headers=headers).json()]
    assert client.get(f"/api/v1/customers/{duplicate.id}", headers=headers).status_code == 200


def test_customer_gstin_identity_remains_branch_scoped(client, auth_headers, admin_user, branch, other_branch):
    headers = auth_headers(admin_user)
    first = client.post("/api/v1/customers", headers=headers, json=customer_payload(branch.id))
    second = client.post("/api/v1/customers", headers=headers, json=customer_payload(other_branch.id))
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_inactive_gstin_cannot_be_recreated(client, auth_headers, staff_user, branch, db_session):
    _legacy_customer(db_session, branch.id, "Disabled buyer", "29ABCDE1234F1Z5", active=False)
    response = client.post("/api/v1/customers", headers=auth_headers(staff_user), json=customer_payload(branch.id))
    assert response.status_code == 422
    assert "inactive" in str(response.json()).lower()
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 1


def test_master_gstin_change_conflicts_but_existing_duplicate_can_be_edited(client, auth_headers, staff_user, branch, db_session):
    first = _legacy_customer(db_session, branch.id, "Buyer A", "29ABCDE1234F1Z5")
    second = _legacy_customer(db_session, branch.id, "Buyer B", "29FGHIJ1234K1Z5")
    duplicate = _legacy_customer(db_session, branch.id, "Legacy buyer A", "29abcde1234f1z5")
    headers = auth_headers(staff_user)
    conflict = client.patch(f"/api/v1/customers/{second.id}", headers=headers, json={"gstin": "29abcde1234f1z5"})
    assert conflict.status_code == 409
    assert "gstin" in str(conflict.json()).lower()
    harmless = client.patch(f"/api/v1/customers/{duplicate.id}", headers=headers, json={"name": "Updated legacy name", "gstin": first.gstin})
    assert harmless.status_code == 200
    assert db_session.get(Customer, second.id).gstin == "29FGHIJ1234K1Z5"


@pytest.mark.parametrize("document_type", ["sales", "reagent"])
def test_inline_buyer_reuses_gstin_and_preserves_manual_buyer_and_consignee_snapshots(client, auth_headers, staff_user, manager_user, branch, db_session, document_type):
    headers = auth_headers(staff_user)
    master = client.post("/api/v1/customers", headers=headers, json={"branch_id": branch.id, **_customer("Existing Buyer", "36ABCDE1234F1Z5")}).json()
    payload = _invoice_payload(branch, buyer=_customer("Transaction Buyer", "36abcde1234f1z5", address_line1="New buyer address"))
    payload["document_type"] = document_type
    if document_type == "reagent":
        manufacturer = client.post("/api/v1/manufacturers", headers=headers, json={"branch_id": branch.id, "code": "SIG", "name": "Sigma"})
        assert manufacturer.status_code == 201
        payload["lines"][0]["manufacturer_id"] = manufacturer.json()["id"]
    payload["consignee"] = _customer("Transaction Warehouse", "36ABCDE1234F1Z5", address_line1="Separate warehouse address")
    response = client.post("/api/v1/invoices", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["buyer_customer_id"] == master["id"]
    assert body["buyer_address_line1"] == "New buyer address"
    assert body["consignee_address_line1"] == "Separate warehouse address"
    assert body["consignee_customer_id"] is None
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 1
    assert db_session.get(Customer, master["id"]).billing_address_line1 == "Billing Street 1"
    edited = client.patch(f"/api/v1/invoices/{body['id']}", headers=headers, json={"expected_version": body["version"], "consignee": deepcopy(payload["consignee"])})
    assert edited.status_code == 200, edited.text
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 1
    submitted = client.post(f"/api/v1/invoices/{body['id']}/submit", headers=headers)
    assert submitted.status_code == 200, submitted.text
    approved = client.post(f"/api/v1/invoices/{body['id']}/approve", headers=auth_headers(manager_user))
    assert approved.status_code == 200, approved.text
    assert approved.json()["buyer_address_line1"] == "New buyer address"
    assert approved.json()["consignee_address_line1"] == "Separate warehouse address"
    assert approved.json()["final_total"] == body["final_total"]
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 1


def test_different_gstin_is_not_reused_by_matching_name_phone(client, auth_headers, staff_user, branch, db_session):
    headers = auth_headers(staff_user)
    original = client.post("/api/v1/invoices", headers=headers, json=_invoice_payload(branch)).json()
    payload = _invoice_payload(branch)
    payload["buyer"]["gstin"] = "36FGHIJ1234K1Z5"
    response = client.post("/api/v1/invoices", headers=headers, json=payload)
    assert response.status_code == 201
    assert response.json()["buyer_customer_id"] != original["buyer_customer_id"]
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 2


def test_postgresql_customer_lock_is_normalized_and_profile_scoped():
    db = Mock()
    db.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    lock_customer_gstin(db, 1, " 29abcde1234f1z5 ")
    first = db.execute.call_args
    lock_customer_gstin(db, 1, "29ABCDE1234F1Z5")
    assert str(first.args[0]) == "SELECT pg_advisory_xact_lock(:key)"
    assert first.args[1] == db.execute.call_args.args[1]
    lock_customer_gstin(db, 2, "29ABCDE1234F1Z5")
    assert first.args[1] != db.execute.call_args.args[1]
    db.reset_mock()
    lock_customer_gstin(db, 1, None)
    db.execute.assert_not_called()


def test_inactive_gstin_cannot_be_used_for_inline_buyer(client, auth_headers, staff_user, branch, db_session):
    _legacy_customer(db_session, branch.id, "Inactive Buyer", "36ABCDE1234F1Z5", active=False)
    response = client.post("/api/v1/invoices", headers=auth_headers(staff_user), json=_invoice_payload(branch))
    assert response.status_code == 422
    assert "inactive" in str(response.json()).lower()
    assert db_session.scalar(select(func.count()).select_from(Customer)) == 1


def test_no_gstin_customers_remain_separate(client, auth_headers, staff_user, branch):
    headers = auth_headers(staff_user)
    payload = customer_payload(branch.id)
    payload["gstin"] = None
    first = client.post("/api/v1/customers", headers=headers, json=payload)
    second = client.post("/api/v1/customers", headers=headers, json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_customer_reactivation_cannot_add_another_active_gstin(client, auth_headers, staff_user, branch, db_session):
    _legacy_customer(db_session, branch.id, "Active buyer", "29ABCDE1234F1Z5")
    inactive = _legacy_customer(db_session, branch.id, "Inactive duplicate", "29abcde1234f1z5", active=False)
    response = client.patch(f"/api/v1/customers/{inactive.id}", headers=auth_headers(staff_user), json={"is_active": True})
    assert response.status_code == 409
    assert not db_session.get(Customer, inactive.id).is_active
