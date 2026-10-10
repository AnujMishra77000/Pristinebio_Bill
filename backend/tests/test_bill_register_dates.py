"""Date registers remain type-separated, bounded and branch-authorized."""
import pytest

from tests.test_financial_correctness import _address, _invoice_payload, _purchase_order_payload


def create_bill(client, auth_headers, user, branch, collection, document_type, bill_date):
    if collection == "invoices":
        payload = _invoice_payload(branch)
        payload["invoice_date"] = bill_date
    else:
        payload = _purchase_order_payload(branch)
        payload["order_date"] = bill_date
    payload["document_type"] = document_type
    if document_type == "reagent":
        response = client.post("/api/v1/manufacturers", headers=auth_headers(user), json={
            "branch_id": branch.id, "name": "Merck", "code": f"M{branch.id}", "is_active": True,
        })
        if response.status_code == 409:
            manufacturers = client.get("/api/v1/manufacturers", headers=auth_headers(user)).json()
            manufacturer_id = next(item["id"] for item in manufacturers if item["branch_id"] == branch.id)
        else:
            assert response.status_code == 201, response.text
            manufacturer_id = response.json()["id"]
        payload["lines"][0]["manufacturer_id"] = manufacturer_id
        if collection == "purchase-orders":
            payload["place_of_supply_state_code"] = "36"
            payload["purchaser"] = {"name": "Research purchaser", "address": _address("Delivery")}
    response = client.post(f"/api/v1/{collection}", headers=auth_headers(user), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


BILL_TYPES = [("invoices", "sales"), ("invoices", "reagent"),
              ("purchase-orders", "domestic_oils"), ("purchase-orders", "reagent")]


@pytest.mark.parametrize("collection,document_type", BILL_TYPES)
def test_register_date_bounds_type_scope_and_stable_pagination(
    client, auth_headers, staff_user, admin_user, branch, other_branch, collection, document_type,
):
    bills = [create_bill(client, auth_headers, staff_user, branch, collection, document_type, day)
             for day in ("2026-09-30", "2026-10-01", "2026-10-01", "2026-10-01", "2026-10-02")]
    other_type = ("reagent" if document_type != "reagent" else
                  "sales" if collection == "invoices" else "domestic_oils")
    create_bill(client, auth_headers, staff_user, branch, collection, other_type, "2026-10-01")
    hidden = create_bill(client, auth_headers, admin_user, other_branch, collection, document_type, "2026-10-01")
    headers = auth_headers(staff_user)
    path = f"/api/v1/{collection}/register?document_type={document_type}&sort=date_desc"
    exact = client.get(path + "&date_from=2026-10-01&date_to=2026-10-01&page_size=2", headers=headers)
    assert exact.status_code == 200, exact.text
    assert exact.json()["total"] == 3
    assert [item["id"] for item in exact.json()["items"]] == [bills[3]["id"], bills[2]["id"]]
    second = client.get(path + "&date_from=2026-10-01&date_to=2026-10-01&page_size=2&page=2", headers=headers)
    assert [item["id"] for item in second.json()["items"]] == [bills[1]["id"]]
    lower = client.get(path + "&date_from=2026-10-02", headers=headers).json()
    assert [item["id"] for item in lower["items"]] == [bills[4]["id"]]
    upper = client.get(path + "&date_to=2026-09-30", headers=headers).json()
    assert [item["id"] for item in upper["items"]] == [bills[0]["id"]]
    ascending = client.get(path.replace("date_desc", "date_asc") + "&date_from=2026-10-01&date_to=2026-10-01", headers=headers).json()
    assert [item["id"] for item in ascending["items"]] == [bill["id"] for bill in bills[1:4]]
    assert client.get(path + "&date_from=2027-01-01", headers=headers).json()["total"] == 0
    assert client.get(f"/api/v1/{collection}/{hidden['id']}", headers=headers).status_code == 403


@pytest.mark.parametrize("collection,document_type", BILL_TYPES)
@pytest.mark.parametrize("query", [
    "date_from=2026-10-02&date_to=2026-10-01", "date_from=not-a-date",
    "date_to=2026-02-30", "date_from=1791072000", "page_size=101",
])
def test_register_rejects_invalid_dates_and_bounds(client, auth_headers, staff_user, collection, document_type, query):
    response = client.get(f"/api/v1/{collection}/register?document_type={document_type}&{query}", headers=auth_headers(staff_user))
    assert response.status_code == 422, response.text


def test_dashboard_counts_all_four_types_without_combining_purchase(
    client, auth_headers, staff_user, admin_user, branch, other_branch,
):
    for count, (collection, document_type) in enumerate(BILL_TYPES, start=1):
        for _ in range(count):
            create_bill(client, auth_headers, staff_user, branch, collection, document_type, "2026-10-01")
    create_bill(client, auth_headers, admin_user, other_branch, "invoices", "sales", "2026-10-01")
    response = client.get("/api/v1/dashboard", headers=auth_headers(staff_user))
    assert response.status_code == 200
    result = response.json()
    assert result["sales_invoice_count"] == 1
    assert result["reagent_invoice_count"] == 2
    assert result["domestic_oils_purchase_order_count"] == 3
    assert result["reagent_purchase_order_count"] == 4
    assert result["purchase_order_count"] == 7
