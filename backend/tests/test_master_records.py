def customer_payload(branch_id: int, name: str = "Apex Laboratories") -> dict:
    return {
        "branch_id": branch_id,
        "name": name,
        "gstin": "29ABCDE1234F1Z5",
        "pan": "ABCDE1234F",
        "email": "billing@apex.example",
        "phone": "9876543210",
        "billing_address": {
            "name": "Apex Billing",
            "address_line1": "Billing Street 1",
            "address_line2": "Industrial Area",
            "city": "Bengaluru",
            "state": "Karnataka",
            "state_code": "29",
            "postal_code": "560001",
        },
        "shipping_address": {
            "name": "Apex Consignee",
            "address_line1": "Shipping Street 2",
            "address_line2": "Warehouse Block",
            "city": "Mysuru",
            "state": "Karnataka",
            "state_code": "29",
            "postal_code": "570001",
        },
        "is_active": True,
    }


def product_payload(branch_id: int, name: str = "Sodium Citrate") -> dict:
    return {
        "branch_id": branch_id,
        "name": name,
        "description": "Tri-sodium citrate dihydrate",
        "hsn_sac": "29181590",
        "unit": "KG",
        "base_rate": "128.7500",
        "gst_rate": "18.00",
        "cess_rate": "0.00",
        "is_active": True,
    }


def test_staff_can_create_customer_for_assigned_branch(client, auth_headers, staff_user, branch):
    response = client.post(
        "/api/v1/customers",
        headers=auth_headers(staff_user),
        json=customer_payload(branch.id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["billing_address"]["address_line1"] == "Billing Street 1"
    assert body["shipping_address"]["address_line1"] == "Shipping Street 2"


def test_staff_cannot_create_customer_for_unassigned_branch(
    client, auth_headers, staff_user, other_branch
):
    response = client.post(
        "/api/v1/customers",
        headers=auth_headers(staff_user),
        json=customer_payload(other_branch.id, "Blocked Customer"),
    )

    assert response.status_code == 403


def test_manager_can_create_product_with_decimal_rates(client, auth_headers, manager_user, branch):
    response = client.post(
        "/api/v1/products",
        headers=auth_headers(manager_user),
        json=product_payload(branch.id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["base_rate"] == "128.7500"
    assert body["gst_rate"] == "18.00"
    assert body["cess_rate"] == "0.00"


def test_staff_cannot_create_product_for_unassigned_branch(
    client, auth_headers, staff_user, other_branch
):
    response = client.post(
        "/api/v1/products",
        headers=auth_headers(staff_user),
        json=product_payload(other_branch.id, "Blocked Product"),
    )

    assert response.status_code == 403


def test_manager_cannot_list_products_for_unassigned_branch(
    client, auth_headers, manager_user, other_branch
):
    response = client.get(
        f"/api/v1/products?branch_id={other_branch.id}",
        headers=auth_headers(manager_user),
    )

    assert response.status_code == 403


def test_product_rejects_negative_rates(client, auth_headers, manager_user, branch):
    payload = product_payload(branch.id, "Invalid Product")
    payload["base_rate"] = "-1.0000"

    response = client.post(
        "/api/v1/products",
        headers=auth_headers(manager_user),
        json=payload,
    )

    assert response.status_code == 422


def test_customer_list_read_and_patch_are_limited_to_assigned_branch(
    client, auth_headers, admin_user, manager_user, branch, other_branch
):
    assigned = client.post(
        "/api/v1/customers",
        headers=auth_headers(admin_user),
        json=customer_payload(branch.id, "Assigned Customer"),
    )
    unassigned = client.post(
        "/api/v1/customers",
        headers=auth_headers(admin_user),
        json=customer_payload(other_branch.id, "Unassigned Customer"),
    )

    list_response = client.get("/api/v1/customers", headers=auth_headers(manager_user))
    scoped_list_response = client.get(
        f"/api/v1/customers?branch_id={other_branch.id}",
        headers=auth_headers(manager_user),
    )
    read_response = client.get(
        f"/api/v1/customers/{unassigned.json()['id']}",
        headers=auth_headers(manager_user),
    )
    patch_response = client.patch(
        f"/api/v1/customers/{unassigned.json()['id']}",
        headers=auth_headers(manager_user),
        json={"name": "Blocked Update"},
    )

    assert assigned.status_code == 201
    assert unassigned.status_code == 201
    assert [item["id"] for item in list_response.json()] == [assigned.json()["id"]]
    assert scoped_list_response.status_code == 403
    assert read_response.status_code == 403
    assert patch_response.status_code == 403


def test_customer_patch_updates_nested_shipping_address_for_assigned_branch(
    client, auth_headers, staff_user, branch
):
    create_response = client.post(
        "/api/v1/customers",
        headers=auth_headers(staff_user),
        json=customer_payload(branch.id),
    )

    patch_response = client.patch(
        f"/api/v1/customers/{create_response.json()['id']}",
        headers=auth_headers(staff_user),
        json={
            "shipping_address": {
                "name": "Updated Consignee",
                "address_line1": "Updated Shipping Street",
                "city": "Pune",
                "state": "Maharashtra",
                "state_code": "27",
                "postal_code": "411001",
            }
        },
    )

    assert create_response.status_code == 201
    assert patch_response.status_code == 200
    assert patch_response.json()["shipping_address"]["address_line1"] == "Updated Shipping Street"


def test_product_list_read_and_patch_are_limited_to_assigned_branch_and_preserve_decimals(
    client, auth_headers, admin_user, manager_user, branch, other_branch
):
    assigned = client.post(
        "/api/v1/products",
        headers=auth_headers(admin_user),
        json=product_payload(branch.id, "Assigned Product"),
    )
    unassigned = client.post(
        "/api/v1/products",
        headers=auth_headers(admin_user),
        json=product_payload(other_branch.id, "Unassigned Product"),
    )

    list_response = client.get("/api/v1/products", headers=auth_headers(manager_user))
    read_response = client.get(
        f"/api/v1/products/{unassigned.json()['id']}",
        headers=auth_headers(manager_user),
    )
    patch_response = client.patch(
        f"/api/v1/products/{unassigned.json()['id']}",
        headers=auth_headers(manager_user),
        json={"base_rate": "99.9900"},
    )
    decimal_patch_response = client.patch(
        f"/api/v1/products/{assigned.json()['id']}",
        headers=auth_headers(manager_user),
        json={"base_rate": "99.9900", "gst_rate": "5.00", "cess_rate": "1.25"},
    )

    assert assigned.status_code == 201
    assert unassigned.status_code == 201
    assert [item["id"] for item in list_response.json()] == [assigned.json()["id"]]
    assert read_response.status_code == 403
    assert patch_response.status_code == 403
    assert decimal_patch_response.status_code == 200
    assert decimal_patch_response.json()["base_rate"] == "99.9900"
    assert decimal_patch_response.json()["gst_rate"] == "5.00"
    assert decimal_patch_response.json()["cess_rate"] == "1.25"
