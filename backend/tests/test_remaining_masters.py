import pytest


def bank_account_payload(branch_id: int, bank_name: str = "State Bank of India") -> dict:
    return {
        "branch_id": branch_id,
        "bank_name": bank_name,
        "account_name": "Pristine Bio",
        "account_number": "12345678901",
        "ifsc_code": "SBIN0001234",
        "branch_name": "Bengaluru Main",
        "is_default": True,
        "is_active": True,
    }


def transporter_payload(branch_id: int, name: str = "Rapid Logistics") -> dict:
    return {
        "branch_id": branch_id,
        "name": name,
        "gstin": "29ABCDE1234F1Z5",
        "phone": "9876543210",
        "vehicle_number": "KA01AB1234",
        "is_active": True,
    }


def terms_payload(branch_id: int, title: str = "Standard Terms") -> dict:
    return {
        "branch_id": branch_id,
        "title": title,
        "body": "Payment due within 30 days.",
        "is_default": True,
        "is_active": True,
    }


def test_admin_can_create_bank_account(client, auth_headers, admin_user, branch):
    response = client.post(
        "/api/v1/bank-accounts",
        headers=auth_headers(admin_user),
        json=bank_account_payload(branch.id),
    )

    assert response.status_code == 201
    assert response.json()["ifsc_code"] == "SBIN0001234"


def test_manager_can_create_transporter_for_assigned_branch(client, auth_headers, manager_user, branch):
    response = client.post(
        "/api/v1/transporters",
        headers=auth_headers(manager_user),
        json=transporter_payload(branch.id),
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Rapid Logistics"


def test_staff_cannot_create_terms_for_unassigned_branch(client, auth_headers, staff_user, other_branch):
    response = client.post(
        "/api/v1/terms-and-conditions",
        headers=auth_headers(staff_user),
        json=terms_payload(other_branch.id, "Blocked Terms"),
    )

    assert response.status_code == 403


def test_staff_can_list_terms_for_assigned_branch(client, auth_headers, staff_user, branch):
    create_response = client.post(
        "/api/v1/terms-and-conditions",
        headers=auth_headers(staff_user),
        json=terms_payload(branch.id),
    )

    assert create_response.status_code == 201
    response = client.get(
        f"/api/v1/terms-and-conditions?branch_id={branch.id}",
        headers=auth_headers(staff_user),
    )
    assert response.status_code == 200
    assert response.json()[0]["title"] == "Standard Terms"


@pytest.mark.parametrize(
    ("path", "payload_factory", "patch_payload"),
    [
        ("bank-accounts", bank_account_payload, {"bank_name": "Updated Bank"}),
        ("transporters", transporter_payload, {"name": "Updated Transporter"}),
        ("terms-and-conditions", terms_payload, {"title": "Updated Terms"}),
    ],
)
def test_remaining_master_list_read_and_patch_deny_unassigned_branch_access(
    client,
    auth_headers,
    admin_user,
    manager_user,
    branch,
    other_branch,
    path,
    payload_factory,
    patch_payload,
):
    assigned = client.post(
        f"/api/v1/{path}",
        headers=auth_headers(admin_user),
        json=payload_factory(branch.id),
    )
    unassigned = client.post(
        f"/api/v1/{path}",
        headers=auth_headers(admin_user),
        json=payload_factory(other_branch.id, "Unassigned Record"),
    )

    list_response = client.get(f"/api/v1/{path}", headers=auth_headers(manager_user))
    scoped_list_response = client.get(
        f"/api/v1/{path}?branch_id={other_branch.id}",
        headers=auth_headers(manager_user),
    )
    read_response = client.get(
        f"/api/v1/{path}/{unassigned.json()['id']}",
        headers=auth_headers(manager_user),
    )
    patch_response = client.patch(
        f"/api/v1/{path}/{unassigned.json()['id']}",
        headers=auth_headers(manager_user),
        json=patch_payload,
    )

    assert assigned.status_code == 201
    assert unassigned.status_code == 201
    assert [item["id"] for item in list_response.json()] == [assigned.json()["id"]]
    assert scoped_list_response.status_code == 403
    assert read_response.status_code == 403
    assert patch_response.status_code == 403


@pytest.mark.parametrize(
    ("path", "payload_factory", "patch_payload", "response_field", "expected_value"),
    [
        ("bank-accounts", bank_account_payload, {"bank_name": "Updated Bank"}, "bank_name", "Updated Bank"),
        ("transporters", transporter_payload, {"name": "Updated Transporter"}, "name", "Updated Transporter"),
        ("terms-and-conditions", terms_payload, {"title": "Updated Terms"}, "title", "Updated Terms"),
    ],
)
def test_remaining_master_patch_updates_assigned_record(
    client,
    auth_headers,
    staff_user,
    branch,
    path,
    payload_factory,
    patch_payload,
    response_field,
    expected_value,
):
    created = client.post(
        f"/api/v1/{path}",
        headers=auth_headers(staff_user),
        json=payload_factory(branch.id),
    )

    response = client.patch(
        f"/api/v1/{path}/{created.json()['id']}",
        headers=auth_headers(staff_user),
        json=patch_payload,
    )

    assert created.status_code == 201
    assert response.status_code == 200
    assert response.json()[response_field] == expected_value


@pytest.mark.parametrize(
    ("path", "payload_factory"),
    [
        ("bank-accounts", bank_account_payload),
        ("transporters", transporter_payload),
        ("terms-and-conditions", terms_payload),
    ],
)
def test_user_cannot_transfer_remaining_master_to_unassigned_branch(
    client,
    auth_headers,
    staff_user,
    branch,
    other_branch,
    path,
    payload_factory,
):
    created = client.post(
        f"/api/v1/{path}",
        headers=auth_headers(staff_user),
        json=payload_factory(branch.id),
    )

    response = client.patch(
        f"/api/v1/{path}/{created.json()['id']}",
        headers=auth_headers(staff_user),
        json={"branch_id": other_branch.id},
    )

    assert created.status_code == 201
    assert response.status_code == 403


@pytest.mark.parametrize(
    ("path", "payload_factory"),
    [
        ("bank-accounts", bank_account_payload),
        ("transporters", transporter_payload),
        ("terms-and-conditions", terms_payload),
    ],
)
def test_admin_cannot_transfer_remaining_master_to_nonexistent_branch(
    client,
    auth_headers,
    admin_user,
    branch,
    path,
    payload_factory,
):
    created = client.post(
        f"/api/v1/{path}",
        headers=auth_headers(admin_user),
        json=payload_factory(branch.id),
    )

    response = client.patch(
        f"/api/v1/{path}/{created.json()['id']}",
        headers=auth_headers(admin_user),
        json={"branch_id": 999999},
    )

    assert created.status_code == 201
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("path", "payload_factory", "missing_field"),
    [
        ("bank-accounts", bank_account_payload, "bank_name"),
        ("transporters", transporter_payload, "name"),
        ("terms-and-conditions", terms_payload, "body"),
    ],
)
def test_remaining_master_create_rejects_missing_required_field(
    client,
    auth_headers,
    admin_user,
    branch,
    path,
    payload_factory,
    missing_field,
):
    payload = payload_factory(branch.id)
    del payload[missing_field]

    response = client.post(
        f"/api/v1/{path}",
        headers=auth_headers(admin_user),
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.parametrize("gstin", ["29ABCDE1234F1Z", "29ABCDE1234F1Z55"])
def test_transporter_create_rejects_gstin_with_invalid_length(
    client,
    auth_headers,
    admin_user,
    branch,
    gstin,
):
    payload = transporter_payload(branch.id)
    payload["gstin"] = gstin

    response = client.post(
        "/api/v1/transporters",
        headers=auth_headers(admin_user),
        json=payload,
    )

    assert response.status_code == 422
