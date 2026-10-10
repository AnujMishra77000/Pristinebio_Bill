import pytest


def _address(state_code: str = "36", line1: str = "Purchaser Industrial Estate") -> dict:
    return {
        "name": "Purchaser Office",
        "address_line1": line1,
        "address_line2": "Phase II",
        "city": "Hyderabad",
        "state": "Telangana" if state_code == "36" else "Karnataka",
        "state_code": state_code,
        "postal_code": "500001" if state_code == "36" else "560001",
    }


def _line() -> dict:
    return {
        "product_name": "Purchaser Test Material",
        "description": "Material for purchaser workflow test",
        "hsn_sac": "28151110",
        "quantity": "2.000",
        "unit": "KG",
        "rate": "100.00",
        "other_charge": "0.00",
        "discount_amount": "0.00",
        "gst_rate": "18.00",
        "cess_rate": "0.00",
    }


def _purchaser(name: str = "Acme Manufacturing Private Limited", *, line1: str = "Purchaser Industrial Estate") -> dict:
    return {
        "name": name,
        "gstin": "36AACCA1234A1Z5",
        "pan": "AACCA1234A",
        "email": "accounts@acme.example",
        "phone": "9876543210",
        "address": _address(line1=line1),
        "is_active": True,
    }


def test_purchaser_master_can_be_created_and_listed(client, auth_headers, staff_user, branch):
    created = client.post(
        "/api/v1/purchasers",
        headers=auth_headers(staff_user),
        json={"branch_id": branch.id, **_purchaser()},
    )

    listed = client.get("/api/v1/purchasers", headers=auth_headers(staff_user))

    assert created.status_code == 201
    assert created.json()["name"] == "Acme Manufacturing Private Limited"
    assert created.json()["address"]["address_line1"] == "Purchaser Industrial Estate"
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [created.json()["id"]]


def test_manual_purchaser_details_are_snapshotted_without_overwriting_master(
    client,
    auth_headers,
    staff_user,
    branch,
):
    master = client.post(
        "/api/v1/purchasers",
        headers=auth_headers(staff_user),
        json={"branch_id": branch.id, **_purchaser(line1="Saved Master Road")},
    )
    assert master.status_code == 201

    response = client.post(
        "/api/v1/purchase-orders",
        headers={**auth_headers(staff_user), "Idempotency-Key": "purchaser-manual-snapshot-1"},
        json={
            "purchaser": _purchaser(line1="New Transaction Road"),
            "save_purchaser_for_future": False,
            "supplier": {
                "name": "Raw Material Provider",
                "address": _address(line1="Supplier Road"),
            },
            "order_date": "2026-09-17",
            "lines": [_line()],
        },
    )

    persisted_master = client.get(
        f"/api/v1/purchasers/{master.json()['id']}",
        headers=auth_headers(staff_user),
    )
    assert response.status_code == 201
    assert response.json()["purchaser_id"] is None
    assert response.json()["purchaser_address_line1"] == "New Transaction Road"
    assert persisted_master.json()["address"]["address_line1"] == "Saved Master Road"


def test_saved_purchaser_is_snapshotted_and_inactive_purchaser_is_rejected(
    client,
    auth_headers,
    staff_user,
    branch,
):
    created = client.post(
        "/api/v1/purchasers",
        headers=auth_headers(staff_user),
        json={"branch_id": branch.id, **_purchaser(name="Saved Purchaser")},
    )
    assert created.status_code == 201

    response = client.post(
        "/api/v1/purchase-orders",
        headers={**auth_headers(staff_user), "Idempotency-Key": "purchaser-saved-snapshot-1"},
        json={
            "purchaser_id": created.json()["id"],
            "supplier": {"name": "Raw Material Provider", "address": _address(line1="Supplier Road")},
            "order_date": "2026-09-17",
            "lines": [_line()],
        },
    )
    assert response.status_code == 201
    assert response.json()["purchaser_id"] == created.json()["id"]
    assert response.json()["purchaser_name"] == "Saved Purchaser"

    disabled = client.patch(
        f"/api/v1/purchasers/{created.json()['id']}",
        headers=auth_headers(staff_user),
        json={"is_active": False},
    )
    rejected = client.post(
        "/api/v1/purchase-orders",
        headers={**auth_headers(staff_user), "Idempotency-Key": "purchaser-inactive-1"},
        json={
            "purchaser_id": created.json()["id"],
            "supplier": {"name": "Raw Material Provider", "address": _address(line1="Supplier Road")},
            "order_date": "2026-09-17",
            "lines": [_line()],
        },
    )

    assert disabled.status_code == 200
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "Purchaser is inactive"


@pytest.mark.parametrize("discount_change", [{"discount_amount": "1.00"}, {"lines": [{**_line(), "discount_amount": "1.00"}]}])
def test_new_purchase_orders_reject_discounts(client, auth_headers, staff_user, discount_change):
    response = client.post(
        "/api/v1/purchase-orders",
        headers=auth_headers(staff_user),
        json={
            "purchaser": _purchaser(name="No Discount Purchaser"),
            "supplier": {"name": "Raw Material Provider", "address": _address(line1="Supplier Road")},
            "order_date": "2026-09-17",
            "lines": [_line()],
            **discount_change,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Discounts are not supported on purchase orders"
