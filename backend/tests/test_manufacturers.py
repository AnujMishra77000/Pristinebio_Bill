def manufacturer_payload(branch_id: int, code: str = "sig", name: str = "Sigma") -> dict:
    return {"branch_id": branch_id, "code": code, "name": name, "is_active": True}


def product_payload(branch_id: int, manufacturer_id: int, code: str = "SIG-001", unit: str = "GM") -> dict:
    return {
        "branch_id": branch_id,
        "manufacturer_id": manufacturer_id,
        "manufacturer_product_code": code,
        "name": "Sodium Citrate",
        "description": "Analytical reagent",
        "hsn_sac": "29181590",
        "unit": unit,
        "base_rate": "30.0000",
        "gst_rate": "18.00",
        "cess_rate": "0.00",
        "is_active": True,
    }


def test_manufacturer_codes_are_normalized_unique_and_deactivatable(client, auth_headers, staff_user, branch):
    created = client.post("/api/v1/manufacturers", headers=auth_headers(staff_user), json=manufacturer_payload(branch.id))
    duplicate = client.post("/api/v1/manufacturers", headers=auth_headers(staff_user), json=manufacturer_payload(branch.id, "SIG", "Sigma Chemicals"))

    assert created.status_code == 201
    assert created.json()["code"] == "SIG"
    assert duplicate.status_code == 409
    deactivated = client.patch(
        f"/api/v1/manufacturers/{created.json()['id']}",
        headers=auth_headers(staff_user),
        json={"is_active": False},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False
    assert client.get("/api/v1/manufacturers?active_only=true", headers=auth_headers(staff_user)).json() == []


def test_manufacturer_and_product_codes_are_branch_scoped_and_units_canonical(client, auth_headers, staff_user, branch):
    manufacturer = client.post("/api/v1/manufacturers", headers=auth_headers(staff_user), json=manufacturer_payload(branch.id)).json()
    product = client.post(
        "/api/v1/products",
        headers=auth_headers(staff_user),
        json=product_payload(branch.id, manufacturer["id"]),
    )
    duplicate_code = client.post(
        "/api/v1/products",
        headers=auth_headers(staff_user),
        json=product_payload(branch.id, manufacturer["id"], "sig-001", "gram"),
    )
    unsupported_unit = client.post(
        "/api/v1/products",
        headers=auth_headers(staff_user),
        json=product_payload(branch.id, manufacturer["id"], "SIG-002", "gallon"),
    )

    assert product.status_code == 201
    assert product.json()["manufacturer_code"] == "SIG"
    assert product.json()["manufacturer_product_code"] == "SIG-001"
    assert product.json()["unit"] == "g"
    assert duplicate_code.status_code == 409
    assert unsupported_unit.status_code == 422


def test_all_supported_business_unit_aliases_normalize_to_standard_symbols(client, auth_headers, staff_user, branch):
    manufacturer = client.post(
        "/api/v1/manufacturers",
        headers=auth_headers(staff_user),
        json=manufacturer_payload(branch.id),
    ).json()
    expected = [("GM", "g"), ("KG", "kg"), ("MG", "mg"), ("μg", "µg"), ("ML", "mL"), ("Liter", "L"), ("TON", "t")]

    for index, (alias, symbol) in enumerate(expected):
        response = client.post(
            "/api/v1/products",
            headers=auth_headers(staff_user),
            json=product_payload(branch.id, manufacturer["id"], f"SIG-{index:03d}", alias),
        )
        assert response.status_code == 201, response.text
        assert response.json()["unit"] == symbol


def test_product_cannot_link_to_inactive_or_unassigned_manufacturer(
    client, auth_headers, staff_user, admin_user, branch, other_branch
):
    manufacturer = client.post(
        "/api/v1/manufacturers",
        headers=auth_headers(admin_user),
        json=manufacturer_payload(other_branch.id),
    ).json()
    blocked_branch = client.post(
        "/api/v1/products",
        headers=auth_headers(staff_user),
        json=product_payload(branch.id, manufacturer["id"]),
    )
    assert blocked_branch.status_code == 422

    local_manufacturer = client.post(
        "/api/v1/manufacturers",
        headers=auth_headers(staff_user),
        json=manufacturer_payload(branch.id, "MRK", "Merck"),
    ).json()
    client.patch(
        f"/api/v1/manufacturers/{local_manufacturer['id']}",
        headers=auth_headers(staff_user),
        json={"is_active": False},
    )
    blocked_inactive = client.post(
        "/api/v1/products",
        headers=auth_headers(staff_user),
        json=product_payload(branch.id, local_manufacturer["id"], "MRK-001"),
    )
    assert blocked_inactive.status_code == 422
