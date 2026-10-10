"""POs need seller details, not a second purchaser form; retain old snapshots."""
import pytest
from sqlalchemy import func, select

from app.models.master_records import Purchaser
from tests.test_financial_correctness import _address, _purchase_order_payload
from tests.test_reagent_purchase_orders import _reagent_payload


def payload_for(kind, client, auth_headers, user, branch):
    payload = _reagent_payload(client, auth_headers, user, branch) if kind == "reagent" else _purchase_order_payload(branch)
    payload.pop("purchaser", None)
    payload.pop("consignee", None)
    return payload


@pytest.mark.parametrize("kind", ["domestic_oils", "reagent"])
def test_po_can_preview_create_retry_and_edit_without_purchaser(client, auth_headers, staff_user, manager_user, branch, db_session, kind):
    payload = payload_for(kind, client, auth_headers, staff_user, branch)
    preview = client.post("/api/v1/purchase-orders/preview", headers=auth_headers(staff_user), json=payload)
    assert preview.status_code == 200, preview.text
    headers = {**auth_headers(staff_user), "Idempotency-Key": f"no-purchaser-{kind}"}
    created = client.post("/api/v1/purchase-orders", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["purchaser_id"] is None and order["purchaser_name"] is None
    for field in ("taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "final_total"):
        assert order[field] == preview.json()[field]
    retried = client.post("/api/v1/purchase-orders", headers=headers, json=payload)
    assert retried.status_code == 200 and retried.json()["id"] == order["id"]
    detail_field = "reagent_details" if kind == "reagent" else "domestic_details"
    updated = client.patch(f"/api/v1/purchase-orders/{order['id']}", headers=auth_headers(staff_user), json={"expected_version": order["version"], detail_field: {**payload, "payment_terms": "45 days"}})
    assert updated.status_code == 200, updated.text
    assert updated.json()["payment_terms"] == "45 days"
    assert updated.json()["purchaser_name"] is None
    assert db_session.scalar(select(func.count(Purchaser.id))) == 0, "No hidden purchaser record should be fabricated"
    version = updated.json()["version"]
    submitted = client.post(f"/api/v1/purchase-orders/{order['id']}/submit", headers=auth_headers(staff_user), json={"expected_version": version})
    assert submitted.status_code == 200, submitted.text
    approved = client.post(f"/api/v1/purchase-orders/{order['id']}/approve", headers=auth_headers(manager_user), json={"expected_version": version})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["final_total"] == preview.json()["final_total"]


@pytest.mark.parametrize("kind", ["domestic_oils", "reagent"])
def test_omitted_purchaser_on_edit_preserves_historical_snapshot(client, auth_headers, staff_user, branch, kind):
    payload = payload_for(kind, client, auth_headers, staff_user, branch)
    payload.update(purchaser={"name": "Historical Purchaser", "address": _address("Historical Purchaser"), "phone": "9876543210", "email": "history@example.org", "is_active": True}, save_purchaser_for_future=True)
    created = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=payload)
    assert created.status_code == 201, created.text
    order = created.json()
    snapshot = {key: value for key, value in order.items() if key.startswith("purchaser_")}
    payload.pop("purchaser")
    payload.pop("save_purchaser_for_future")
    detail_field = "reagent_details" if kind == "reagent" else "domestic_details"
    updated = client.patch(f"/api/v1/purchase-orders/{order['id']}", headers=auth_headers(staff_user), json={"expected_version": order["version"], detail_field: {**payload, "payment_terms": "60 days"}})
    assert updated.status_code == 200, updated.text
    assert {key: value for key, value in updated.json().items() if key.startswith("purchaser_")} == snapshot
    # Explicit clearing remains distinct from omission for compatible API clients.
    cleared = client.patch(f"/api/v1/purchase-orders/{order['id']}", headers=auth_headers(staff_user), json={"expected_version": updated.json()["version"], detail_field: {**payload, "purchaser_id": None, "purchaser": None}})
    assert cleared.status_code == 200, cleared.text
    assert all(value is None for key, value in cleared.json().items() if key.startswith("purchaser_"))
