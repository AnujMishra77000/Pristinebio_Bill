def supplier_payload(branch_id: int, name: str = "Default Raw Material Provider") -> dict:
    return {
        "branch_id": branch_id,
        "name": name,
        "gstin": "36ABCDE1234F1Z5",
        "address": {
            "name": name,
            "address_line1": "Industrial Supplier Road",
            "address_line2": "Warehouse 4",
            "city": "Hyderabad",
            "state": "Telangana",
            "state_code": "36",
            "postal_code": "500001",
        },
        "is_active": True,
    }


def test_supplier_default_can_be_selected_and_replaces_previous_default(
    client,
    auth_headers,
    staff_user,
    branch,
):
    first = client.post(
        "/api/v1/suppliers",
        headers=auth_headers(staff_user),
        json={**supplier_payload(branch.id), "is_default": True},
    )
    second = client.post(
        "/api/v1/suppliers",
        headers=auth_headers(staff_user),
        json={
            **supplier_payload(branch.id, "Second Raw Material Provider"),
            "gstin": "36ABCDE1234F2Z5",
            "is_default": True,
        },
    )

    first_after = client.get(
        f"/api/v1/suppliers/{first.json()['id']}",
        headers=auth_headers(staff_user),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["is_default"] is True
    assert second.json()["is_default"] is True
    assert first_after.json()["is_default"] is False


def test_inactive_supplier_cannot_be_default_and_deactivation_clears_default(
    client,
    auth_headers,
    staff_user,
    branch,
):
    invalid = client.post(
        "/api/v1/suppliers",
        headers=auth_headers(staff_user),
        json={**supplier_payload(branch.id), "is_active": False, "is_default": True},
    )
    created = client.post(
        "/api/v1/suppliers",
        headers=auth_headers(staff_user),
        json={**supplier_payload(branch.id), "is_default": True},
    )
    deactivated = client.patch(
        f"/api/v1/suppliers/{created.json()['id']}",
        headers=auth_headers(staff_user),
        json={"is_active": False},
    )

    assert invalid.status_code == 422
    assert invalid.json()["detail"] == "Only active suppliers can be set as default"
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert deactivated.json()["is_default"] is False


def test_unused_supplier_can_be_deleted_permanently(
    client,
    auth_headers,
    staff_user,
    branch,
):
    created = client.post(
        "/api/v1/suppliers",
        headers=auth_headers(staff_user),
        json=supplier_payload(branch.id),
    )

    deleted = client.delete(
        f"/api/v1/suppliers/{created.json()['id']}",
        headers=auth_headers(staff_user),
    )
    missing = client.get(
        f"/api/v1/suppliers/{created.json()['id']}",
        headers=auth_headers(staff_user),
    )

    assert deleted.status_code == 204
    assert missing.status_code == 404
