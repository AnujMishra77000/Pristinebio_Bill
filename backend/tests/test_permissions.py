def test_admin_can_list_all_branches(client, auth_headers, admin_user, branch, other_branch):
    response = client.get("/api/v1/branches", headers=auth_headers(admin_user))

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert {branch.id, other_branch.id}.issubset(ids)


def test_manager_lists_only_assigned_branches(
    client, auth_headers, manager_user, branch, other_branch
):
    response = client.get("/api/v1/branches", headers=auth_headers(manager_user))

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert branch.id in ids
    assert other_branch.id not in ids


def test_manager_cannot_read_unassigned_branch(
    client, auth_headers, manager_user, other_branch
):
    response = client.get(
        f"/api/v1/branches/{other_branch.id}", headers=auth_headers(manager_user)
    )

    assert response.status_code == 403


def test_staff_cannot_create_branch(client, auth_headers, staff_user, company):
    response = client.post(
        "/api/v1/branches",
        headers=auth_headers(staff_user),
        json={
            "company_id": company.id,
            "name": "Blocked Branch",
            "gstin": "29ABCDE1234F2Z7",
            "address_line1": "Blocked Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "state_code": "29",
            "postal_code": "560001",
            "is_active": True,
        },
    )

    assert response.status_code == 403


def test_staff_cannot_create_company(client, auth_headers, staff_user):
    response = client.post(
        "/api/v1/companies",
        headers=auth_headers(staff_user),
        json={"legal_name": "Blocked Company Private Limited"},
    )

    assert response.status_code == 403


def test_staff_cannot_patch_assigned_branch(client, auth_headers, staff_user, branch):
    response = client.patch(
        f"/api/v1/branches/{branch.id}",
        headers=auth_headers(staff_user),
        json={"name": "Blocked Update"},
    )

    assert response.status_code == 403


def test_manager_cannot_patch_reachable_company(
    client, auth_headers, manager_user, company
):
    response = client.patch(
        f"/api/v1/companies/{company.id}",
        headers=auth_headers(manager_user),
        json={"trade_name": "Blocked Update"},
    )

    assert response.status_code == 403


def test_manager_can_list_and_read_only_reachable_companies(
    client, auth_headers, manager_user, company
):
    list_response = client.get("/api/v1/companies", headers=auth_headers(manager_user))
    read_response = client.get(
        f"/api/v1/companies/{company.id}", headers=auth_headers(manager_user)
    )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [company.id]
    assert read_response.status_code == 200
    assert read_response.json()["id"] == company.id


def test_manager_cannot_read_unassigned_company(client, auth_headers, admin_user, manager_user):
    create_response = client.post(
        "/api/v1/companies",
        headers=auth_headers(admin_user),
        json={"legal_name": "Unassigned Company Private Limited"},
    )

    response = client.get(
        f"/api/v1/companies/{create_response.json()['id']}",
        headers=auth_headers(manager_user),
    )

    assert create_response.status_code == 201
    assert response.status_code == 403


def test_staff_lists_and_reads_only_assigned_branches(
    client, auth_headers, staff_user, branch, other_branch
):
    list_response = client.get("/api/v1/branches", headers=auth_headers(staff_user))
    read_response = client.get(
        f"/api/v1/branches/{branch.id}", headers=auth_headers(staff_user)
    )
    denied_response = client.get(
        f"/api/v1/branches/{other_branch.id}", headers=auth_headers(staff_user)
    )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [branch.id]
    assert read_response.status_code == 200
    assert read_response.json()["id"] == branch.id
    assert denied_response.status_code == 403


def test_admin_can_create_and_patch_company(client, auth_headers, admin_user):
    create_response = client.post(
        "/api/v1/companies",
        headers=auth_headers(admin_user),
        json={
            "legal_name": "New Company Private Limited",
            "trade_name": "New Company",
            "pan": "BBBBB1111B",
            "registered_address": "2 Company Street",
            "is_active": True,
        },
    )

    assert create_response.status_code == 201
    company_id = create_response.json()["id"]

    patch_response = client.patch(
        f"/api/v1/companies/{company_id}",
        headers=auth_headers(admin_user),
        json={"trade_name": "Updated Company"},
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["trade_name"] == "Updated Company"


def test_admin_can_create_and_patch_branch(client, auth_headers, admin_user, company):
    create_response = client.post(
        "/api/v1/branches",
        headers=auth_headers(admin_user),
        json={
            "company_id": company.id,
            "name": "New Branch",
            "gstin": "29ABCDE1234F2Z7",
            "address_line1": "New Branch Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "state_code": "29",
            "postal_code": "560001",
            "is_active": True,
        },
    )

    assert create_response.status_code == 201
    branch_id = create_response.json()["id"]

    patch_response = client.patch(
        f"/api/v1/branches/{branch_id}",
        headers=auth_headers(admin_user),
        json={"name": "Updated Branch"},
    )

    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Updated Branch"


def test_branch_payload_requires_a_fifteen_character_gstin(
    client, auth_headers, admin_user, company
):
    response = client.post(
        "/api/v1/branches",
        headers=auth_headers(admin_user),
        json={
            "company_id": company.id,
            "name": "Invalid GSTIN Branch",
            "gstin": "TOO-SHORT",
            "address_line1": "Validation Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "state_code": "29",
            "postal_code": "560001",
        },
    )

    assert response.status_code == 422


def test_branch_create_rejects_duplicate_gstin(
    client, auth_headers, admin_user, branch, company
):
    response = client.post(
        "/api/v1/branches",
        headers=auth_headers(admin_user),
        json={
            "company_id": company.id,
            "name": "Duplicate GSTIN Branch",
            "gstin": branch.gstin,
            "address_line1": "Duplicate Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "state_code": "29",
            "postal_code": "560001",
        },
    )

    assert response.status_code == 409


def test_branch_patch_requires_a_fifteen_character_gstin(
    client, auth_headers, admin_user, branch
):
    response = client.patch(
        f"/api/v1/branches/{branch.id}",
        headers=auth_headers(admin_user),
        json={"gstin": "TOO-SHORT"},
    )

    assert response.status_code == 422
