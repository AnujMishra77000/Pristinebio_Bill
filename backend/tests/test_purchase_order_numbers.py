from datetime import UTC, datetime
import hashlib
import json

import pytest
from sqlalchemy import func, select

from app.models.purchase_order import PurchaseOrder, PurchaseOrderCreationRequest, PurchaseOrderRevision
from app.schemas.purchase_order import PurchaseOrderCreate
from app.services.invoice_pdf import (
    build_invoice_html,
    build_purchase_order_context,
    build_reagent_purchase_order_context,
)
from tests.test_financial_correctness import _purchase_order_payload
from tests.test_reagent_purchase_orders import _reagent_payload


def payload_for(document_type, client, auth_headers, staff_user, branch):
    if document_type == "reagent":
        return _reagent_payload(client, auth_headers, staff_user, branch)
    return _purchase_order_payload(branch)


@pytest.mark.parametrize("document_type", ["domestic_oils", "reagent"])
def test_manual_po_number_survives_retry_approval_and_pdf_header(
    document_type, client, auth_headers, staff_user, manager_user, branch, company, db_session
):
    payload = payload_for(document_type, client, auth_headers, staff_user, branch)
    payload["purchase_order_number"] = "  CLIENT/PO-2026/0042  "
    headers = {**auth_headers(staff_user), "Idempotency-Key": "manual-po-save"}
    created = client.post("/api/v1/purchase-orders", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["purchase_order_number"] == "CLIENT/PO-2026/0042"
    replay = client.post("/api/v1/purchase-orders", headers=headers, json=payload)
    assert replay.status_code == 200 and replay.json()["id"] == order["id"]
    assert db_session.scalar(select(func.count()).select_from(PurchaseOrder)) == 1
    changed_intent = client.post(
        "/api/v1/purchase-orders", headers=headers,
        json={**payload, "purchase_order_number": "CLIENT/PO-2026/0043"},
    )
    assert changed_intent.status_code == 409
    url = f"/api/v1/purchase-orders/{order['id']}"
    assert client.post(url + "/submit", headers=auth_headers(staff_user), json={"expected_version": 1}).status_code == 200
    approved = client.post(url + "/approve", headers=auth_headers(manager_user), json={"expected_version": 1})
    assert approved.status_code == 200, approved.text
    assert approved.json()["purchase_order_number"] == order["purchase_order_number"]
    stored = db_session.get(PurchaseOrder, order["id"])
    builder = build_reagent_purchase_order_context if document_type == "reagent" else build_purchase_order_context
    context = builder(stored, company=company, branch=branch, generated_at=datetime.now(UTC))
    assert context.invoice_number == "CLIENT/PO-2026/0042"
    assert "CLIENT/PO-2026/0042" in build_invoice_html(context)
    rejected = client.patch(url, headers=auth_headers(staff_user), json={"expected_version": 1, "purchase_order_number": "RENUMBERED"})
    assert rejected.status_code == 409
    amended = client.post(url + "/amend", headers=auth_headers(staff_user), json={"expected_version": 1, "reason": "Correct delivery"})
    assert amended.status_code == 200, amended.text
    assert client.patch(url, headers=auth_headers(staff_user), json={"expected_version": amended.json()["version"], "purchase_order_number": "RENUMBERED"}).status_code == 409
    assert db_session.get(PurchaseOrder, order["id"]).purchase_order_number == "CLIENT/PO-2026/0042"


def test_duplicate_po_number_is_shared_across_types_and_case_insensitive(
    client, auth_headers, staff_user, branch, db_session
):
    original_payload = _purchase_order_payload(branch)
    original_payload["purchase_order_number"] = "CLIENT-001"
    original = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=original_payload)
    assert original.status_code == 201
    # Older stored numbers may not have been canonicalized; do not rewrite them.
    stored = db_session.get(PurchaseOrder, original.json()["id"])
    stored.purchase_order_number = "client-001"
    db_session.commit()
    reagent = _reagent_payload(client, auth_headers, staff_user, branch)
    reagent["purchase_order_number"] = "ClIeNt-001"
    duplicate = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=reagent)
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["field"] == "purchase_order_number"
    assert db_session.scalar(select(func.count()).select_from(PurchaseOrder)) == 1
    assert db_session.get(PurchaseOrder, stored.id).purchase_order_number == "client-001"


@pytest.mark.parametrize("first_type", ["domestic_oils", "reagent"])
def test_po_types_share_numbers_but_keep_separate_register_and_dashboard_counts(
    first_type, client, auth_headers, staff_user, branch, db_session
):
    payloads = {
        "domestic_oils": _purchase_order_payload(branch),
        "reagent": _reagent_payload(client, auth_headers, staff_user, branch),
    }
    second_type = "reagent" if first_type == "domestic_oils" else "domestic_oils"
    headers = auth_headers(staff_user)
    original = client.post(
        "/api/v1/purchase-orders", headers=headers,
        json={**payloads[first_type], "purchase_order_number": "SHARED-001"},
    )
    assert original.status_code == 201, original.text
    duplicate = client.post(
        "/api/v1/purchase-orders", headers=headers,
        json={**payloads[second_type], "purchase_order_number": " shared-001 "},
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["field"] == "purchase_order_number"
    assert db_session.scalar(select(func.count()).select_from(PurchaseOrder)) == 1

    second_payload = {**payloads[second_type], "purchase_order_number": "SHARED-002"}
    retry_headers = {**headers, "Idempotency-Key": "shared-po-second-save"}
    second = client.post("/api/v1/purchase-orders", headers=retry_headers, json=second_payload)
    assert second.status_code == 201, second.text
    replay = client.post("/api/v1/purchase-orders", headers=retry_headers, json=second_payload)
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == second.json()["id"]

    collision = client.patch(
        f"/api/v1/purchase-orders/{second.json()['id']}", headers=headers,
        json={"expected_version": second.json()["version"], "purchase_order_number": "SHARED-001"},
    )
    assert collision.status_code == 409, collision.text
    assert db_session.get(PurchaseOrder, second.json()["id"]).purchase_order_number == "SHARED-002"
    third = client.post(
        "/api/v1/purchase-orders", headers=headers,
        json={**payloads[first_type], "purchase_order_number": "SHARED-003"},
    )
    assert third.status_code == 201, third.text
    assert len({order.json()["purchase_order_number"] for order in (original, second, third)}) == 3

    dashboard = client.get("/api/v1/dashboard", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["purchase_order_count"] == 3
    for document_type, count in ((first_type, 2), (second_type, 1)):
        register = client.get(
            f"/api/v1/purchase-orders/register?document_type={document_type}", headers=headers,
        )
        assert register.status_code == 200, register.text
        assert register.json()["total"] == count
        assert all(order["document_type"] == document_type for order in register.json()["items"])
        assert dashboard.json()[f"{document_type}_purchase_order_count"] == count


@pytest.mark.parametrize("invalid", ["", "   ", "A" * 101, "PO\n001", "PO\x00-001"])
def test_invalid_manual_po_numbers_have_field_validation_errors(invalid, client, auth_headers, staff_user, branch):
    payload = {**_purchase_order_payload(branch), "purchase_order_number": invalid}
    response = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=payload)
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"][-1] == "purchase_order_number"


@pytest.mark.parametrize("document_type", ["domestic_oils", "reagent"])
def test_draft_po_number_edit_is_versioned_and_invalidates_old_pdf(
    document_type, client, auth_headers, staff_user, branch, db_session
):
    payload = payload_for(document_type, client, auth_headers, staff_user, branch)
    payload["purchase_order_number"] = "BEFORE-001"
    created = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=payload).json()
    url = f"/api/v1/purchase-orders/{created['id']}"
    stored = db_session.get(PurchaseOrder, created["id"])
    stored.pdf_storage_key = "historical-file.pdf"
    db_session.commit()
    patch = {"expected_version": 1, "purchase_order_number": "AFTER-001"}
    if document_type == "reagent":
        patch = {"expected_version": 1, "reagent_details": {**payload, "purchase_order_number": "AFTER-001"}}
    changed = client.patch(url, headers=auth_headers(staff_user), json=patch)
    assert changed.status_code == 200, changed.text
    assert changed.json()["purchase_order_number"] == "AFTER-001"
    assert changed.json()["version"] == 2
    assert changed.json()["pdf_storage_key"] is None
    revisions = list(db_session.scalars(select(PurchaseOrderRevision).where(PurchaseOrderRevision.purchase_order_id == created["id"]).order_by(PurchaseOrderRevision.revision)))
    assert "BEFORE-001" in str(revisions[0].snapshot)
    assert "AFTER-001" in str(revisions[1].snapshot)
    stale = client.patch(url, headers=auth_headers(staff_user), json=patch)
    assert stale.status_code == 409
    for value in (None, ""):
        rejected = client.patch(url, headers=auth_headers(staff_user), json={"expected_version": 2, "purchase_order_number": value})
        assert rejected.status_code == 422
    assert client.patch(url, headers=auth_headers(staff_user), json={"purchase_order_number": "NO-VERSION"}).status_code == 422


def test_duplicate_draft_number_edit_preserves_existing_data(client, auth_headers, staff_user, branch, db_session):
    payload = _purchase_order_payload(branch)
    for number in ("TAKEN-001", "EDIT-001"):
        created = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json={**payload, "purchase_order_number": number})
        assert created.status_code == 201
    order = created.json()
    response = client.patch(f"/api/v1/purchase-orders/{order['id']}", headers=auth_headers(staff_user), json={"expected_version": 1, "purchase_order_number": "TAKEN-001", "payment_terms": "Must not persist"})
    assert response.status_code == 409, response.text
    current = db_session.get(PurchaseOrder, order["id"])
    assert current.purchase_order_number == "EDIT-001"
    assert current.payment_terms == order["payment_terms"] and current.version == 1


def test_omitted_manual_number_preserves_automatic_po_numbering(client, auth_headers, staff_user, branch):
    created = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=_purchase_order_payload(branch))
    assert created.status_code == 201, created.text
    assert created.json()["purchase_order_number"].startswith(f"PO-{branch.gstin}/2026-27/")


@pytest.mark.parametrize("first_type", ["domestic_oils", "reagent"])
def test_database_unique_conflict_returns_field_error_when_precheck_misses_a_race(
    first_type, client, auth_headers, staff_user, branch, db_session, monkeypatch
):
    payloads = {
        "domestic_oils": _purchase_order_payload(branch),
        "reagent": _reagent_payload(client, auth_headers, staff_user, branch),
    }
    payload = {**payloads[first_type], "purchase_order_number": "RACING-001"}
    created = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=payload)
    assert created.status_code == 201
    original_scalar = db_session.scalar

    def missed_precheck(statement, *args, **kwargs):
        # Simulate a concurrent winner not yet visible to the advisory SELECT.
        # The actual database UNIQUE constraint still runs and rejects the save.
        if "upper(purchase_orders.purchase_order_number)" in str(statement):
            return None
        return original_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "scalar", missed_precheck)
    second_type = "reagent" if first_type == "domestic_oils" else "domestic_oils"
    duplicate = client.post(
        "/api/v1/purchase-orders", headers=auth_headers(staff_user),
        json={**payloads[second_type], "purchase_order_number": "RACING-001"},
    )
    assert duplicate.status_code == 409, duplicate.text
    assert duplicate.json()["detail"]["field"] == "purchase_order_number"
    assert original_scalar(select(func.count()).select_from(PurchaseOrder)) == 1


def test_creation_retry_with_legacy_payload_hash_preserves_original_order(
    client, auth_headers, staff_user, branch, db_session
):
    payload = _purchase_order_payload(branch)
    headers = {**auth_headers(staff_user), "Idempotency-Key": "existing-client-save"}
    created = client.post("/api/v1/purchase-orders", headers=headers, json=payload)
    assert created.status_code == 201
    # Simulate the durable hash written before the optional PO number existed.
    legacy_payload = PurchaseOrderCreate.model_validate(payload).model_dump(mode="json", exclude={"purchase_order_number"})
    for line in legacy_payload["lines"]:
        line.pop("pack_size", None)  # absent in the actual pre-field durable hash
    serialized = json.dumps(legacy_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    record = db_session.scalar(select(PurchaseOrderCreationRequest).where(PurchaseOrderCreationRequest.idempotency_key == "existing-client-save"))
    record.payload_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    db_session.commit()
    replay = client.post("/api/v1/purchase-orders", headers=headers, json=payload)
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == created.json()["id"]
    assert replay.json()["purchase_order_number"] == created.json()["purchase_order_number"]
    different = client.post("/api/v1/purchase-orders", headers=headers, json={**payload, "purchase_order_number": "NEW-INTENT"})
    assert different.status_code == 409
