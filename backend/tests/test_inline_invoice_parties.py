"""Same-ID invoice editing keeps inline transaction parties independent of masters."""

from copy import deepcopy

import pytest
from sqlalchemy import select

from app.models.invoice import Invoice, InvoiceRevision
from app.models.master_records import Customer
from tests.test_financial_correctness import _address, _customer
from tests.test_inline_submission import _document, _state


@pytest.mark.parametrize("document_type", ["sales", "reagent_bill"])
def test_full_inline_invoice_patch_preserves_edited_parties_and_recalculates_same_document(
    document_type, client, auth_headers, staff_user, manager_user, branch, db_session,
):
    url, original, payload = _document(document_type, client, auth_headers, staff_user, branch)
    masters = _state(db_session, (Customer,))
    updated = deepcopy(payload)
    updated.pop("document_type", None)
    updated["buyer_customer_id"] = None
    updated["buyer"] = _customer("Transaction Buyer", "36ABCDE1234F1Z5", address_line1="Edited buyer street")
    updated["buyer"]["email"] = "transaction@example.com"
    updated["consignee_customer_id"] = None
    updated["consignee"] = _customer("Edited Warehouse", "36ABCDE1234F1Z5", address_line1="Edited warehouse street")
    updated["consignee"]["pan"] = "FGHIJ1234K"
    updated["consignee"]["email"] = "warehouse@example.com"
    updated["invoice_number_suffix"] = "EDITED-001"
    updated["invoice_date"] = "2026-10-03"
    updated["payment_terms"] = "Edited payment terms"
    updated["vehicle_number"] = "TS09EDIT01"
    updated["lines"][0]["quantity"] = "3.000"
    updated["expected_version"] = original["version"]
    headers = auth_headers(staff_user)
    response = client.patch(url, headers=headers, json=updated)
    assert response.status_code == 200, response.text
    document = response.json()
    assert document["id"] == original["id"] and document["version"] == 2
    assert document["status"] == "draft"
    assert document["invoice_number"] == "PBPL/2026-27/EDITED-001"
    assert document["buyer_name"] == "Transaction Buyer"
    assert document["buyer_address_line1"] == "Edited buyer street"
    assert document["buyer_email"] == "transaction@example.com"
    assert document["consignee_name"] == "Edited Warehouse Office"
    assert document["consignee_address_line1"] == "Edited warehouse street"
    assert document["consignee_pan"] == "FGHIJ1234K" and document["consignee_email"] == "warehouse@example.com"
    assert document["payment_terms"] == "Edited payment terms" and document["vehicle_number"] == "TS09EDIT01"
    assert document["lines"][0]["quantity"] == "3.000"
    assert document["final_total"] == ("284.00" if document_type == "reagent_bill" else "354.00")
    if document_type == "reagent_bill":
        assert document["lines"][0]["manufacturer_name"] == "Merck"
        assert document["lines"][0]["manufacturer_product_code"] == "MRK-007"
    # Existing buyers stay intact; a separately named consignee may become a new master.
    current_masters = _state(db_session, (Customer,))["customers"]
    assert current_masters[:len(masters["customers"])] == masters["customers"]
    assert len(list(db_session.scalars(select(Invoice)))) == 1
    revisions = list(db_session.scalars(select(InvoiceRevision).where(InvoiceRevision.invoice_id == original["id"]).order_by(InvoiceRevision.revision)))
    assert [revision.event for revision in revisions] == ["created", "draft_updated"]
    assert revisions[0].snapshot["buyer"]["name"] == "Invoice Buyer"
    assert revisions[1].snapshot["buyer"]["name"] == "Transaction Buyer"
    assert revisions[1].snapshot["buyer"]["email"] == "transaction@example.com"
    assert revisions[1].snapshot["buyer"]["pan"] == "ABCDE1234F"
    assert revisions[1].snapshot["consignee"]["address_line1"] == "Edited warehouse street"
    assert client.post(url + "/submit", headers=headers, json={"expected_version": 2}).status_code == 200
    approved = client.post(url + "/approve", headers=auth_headers(manager_user), json={"expected_version": 2})
    assert approved.status_code == 200, approved.text
    assert approved.json()["buyer_name"] == "Transaction Buyer"
    assert approved.json()["consignee_address_line1"] == "Edited warehouse street"


def test_explicit_null_consignee_uses_current_buyer_snapshot_without_master_replacement(
    client, auth_headers, staff_user, branch, db_session,
):
    url, original, _ = _document("sales", client, auth_headers, staff_user, branch)
    db_session.get(Customer, original["buyer_customer_id"]).billing_address_line1 = "Changed master street"
    db_session.commit()
    headers = auth_headers(staff_user)
    edited = client.patch(url, headers=headers, json={
        "expected_version": 1,
        "buyer_customer_id": None,
        "buyer": _customer("Inline Buyer", "36ABCDE1234F1Z5", address_line1="Inline buyer street"),
        "consignee_customer_id": None,
        "consignee": _customer("Separate Consignee", "36ABCDE1234F1Z5", address_line1="Separate street"),
    })
    assert edited.status_code == 200, edited.text
    cleared = client.patch(url, headers=headers, json={"expected_version": 2, "consignee": None, "consignee_customer_id": None})
    assert cleared.status_code == 200, cleared.text
    value = cleared.json()
    for field in ("name", "gstin", "pan", "email", "phone", "address_line1", "address_line2", "city", "state", "state_code", "postal_code"):
        assert value[f"consignee_{field}"] == value[f"buyer_{field}"]
    assert value["consignee_customer_id"] == value["buyer_customer_id"]
    assert value["consignee_address_line1"] == "Inline buyer street"
    unchanged = client.patch(url, headers=headers, json={"expected_version": 3, "payment_terms": "Only metadata"})
    assert unchanged.status_code == 200
    assert unchanged.json()["consignee_address_line1"] == "Inline buyer street"


def test_invoice_can_switch_between_saved_and_manual_parties_with_explicit_null_ids(
    client, auth_headers, staff_user, branch, db_session,
):
    url, original, _ = _document("sales", client, auth_headers, staff_user, branch)
    headers = auth_headers(staff_user)
    manual = client.patch(url, headers=headers, json={"expected_version": 1, "buyer_customer_id": None, "buyer": _customer("Manual Buyer", "36ABCDE1234F1Z5", address_line1="Manual street")})
    assert manual.status_code == 200, manual.text
    assert manual.json()["buyer_name"] == "Manual Buyer"
    assert manual.json()["buyer_customer_id"] == original["buyer_customer_id"]
    saved = client.patch(url, headers=headers, json={"expected_version": 2, "buyer": None, "buyer_customer_id": original["buyer_customer_id"], "consignee": None})
    assert saved.status_code == 200, saved.text
    assert saved.json()["buyer_name"] == "Invoice Buyer"
    assert saved.json()["consignee_name"] == "Invoice Buyer"
    assert db_session.get(Customer, original["buyer_customer_id"]).name == "Invoice Buyer"


@pytest.mark.parametrize("invalid,expected_status", [("null_buyer", 422), ("inactive_buyer", 422), ("inactive_inline_with_saved_id", 422), ("wrong_buyer_branch", 422), ("wrong_consignee_branch", 422), ("wrong_document_branch", 422), ("stale_version", 409), ("missing_version", 422), ("invalid_line", 422)])
def test_inline_invoice_party_failures_leave_document_masters_and_revisions_unchanged(
    invalid, expected_status, client, auth_headers, staff_user, branch, other_branch, db_session,
):
    url, original, _ = _document("sales", client, auth_headers, staff_user, branch)
    patch = {"expected_version": 1, "buyer_customer_id": None, "buyer": _customer("Edited Buyer", "36ABCDE1234F1Z5"), "payment_terms": "Must not persist"}
    if invalid == "null_buyer": patch["buyer"] = None
    if invalid == "inactive_buyer": patch["buyer"]["is_active"] = False
    if invalid == "inactive_inline_with_saved_id":
        patch["buyer_customer_id"] = original["buyer_customer_id"]
        patch["buyer"]["is_active"] = False
    if invalid == "wrong_buyer_branch": patch["buyer"]["branch_id"] = other_branch.id
    if invalid == "wrong_consignee_branch": patch["consignee"] = {**_customer("Consignee", "36ABCDE1234F1Z5"), "branch_id": other_branch.id}
    if invalid == "wrong_document_branch": patch["branch_id"] = other_branch.id
    if invalid == "stale_version": patch["expected_version"] = 2
    if invalid == "missing_version": patch.pop("expected_version")
    if invalid == "invalid_line": patch["lines"] = [{"quantity": "1.000", "rate": "10.00"}]
    headers = auth_headers(staff_user)
    before = _state(db_session)
    response = client.patch(url, headers=headers, json=patch)
    assert response.status_code == expected_status, response.text
    db_session.expire_all()
    assert _state(db_session) == before


def test_inline_invoice_party_edit_is_blocked_after_submission_and_for_unassigned_branch(
    client, auth_headers, staff_user, admin_user, branch, other_branch, db_session,
):
    url, _, _ = _document("sales", client, auth_headers, staff_user, branch)
    headers = auth_headers(staff_user)
    assert client.post(url + "/submit", headers=headers, json={"expected_version": 1}).status_code == 200
    patch = {"expected_version": 1, "buyer": _customer("Attempted Buyer", "36ABCDE1234F1Z5")}
    before = _state(db_session)
    assert client.patch(url, headers=headers, json=patch).status_code == 409
    assert _state(db_session) == before
    other_url, _, _ = _document("sales", client, auth_headers, admin_user, other_branch)
    assert client.patch(other_url, headers=headers, json=patch).status_code == 403
