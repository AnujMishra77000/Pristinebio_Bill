import hashlib
from types import SimpleNamespace

from sqlalchemy import select

from app.api.v1 import purchase_orders
from app.models.invoice import InvoiceRevision
from app.models.master_records import Customer, Product


def test_sales_invoice_requires_seller_gst_profile_when_none_is_configured(
    client,
    auth_headers,
    admin_user,
):
    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(admin_user),
        json={
            "buyer": {
                "name": "Fresh Vendor",
                "billing_address": _manual_address("36"),
            },
            "invoice_date": "2026-08-30",
            "invoice_number_suffix": "MANUAL-001",
            "place_of_supply_state_code": "36",
            "lines": [_manual_line()],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Seller/GST profile is not configured for this user"


def test_purchase_order_requires_seller_gst_profile_when_none_is_configured(
    client,
    auth_headers,
    admin_user,
):
    response = client.post(
        "/api/v1/purchase-orders",
        headers=auth_headers(admin_user),
        json={
            "supplier": {
                "name": "Raw Material Provider",
                "address": _manual_address("36"),
            },
            "order_date": "2026-08-30",
            "lines": [_manual_line()],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Seller/GST profile is not configured for this user"


def _manual_address(state_code: str = "36") -> dict:
    return {
        "name": "Manual Party Office",
        "address_line1": "Plot 42, Industrial Estate",
        "address_line2": "Phase II",
        "city": "Hyderabad",
        "state": "Telangana" if state_code == "36" else "Karnataka",
        "state_code": state_code,
        "postal_code": "500001" if state_code == "36" else "560001",
    }


def _manual_line(name: str = "Caustic Soda Flakes") -> dict:
    return {
        "product_name": name,
        "description": "Manual raw material line saved from first billing entry",
        "hsn_sac": "28151110",
        "quantity": "10.000",
        "unit": "KG",
        "rate": "100.00",
        "other_charge": "0.00",
        "discount_amount": "0.00",
        "gst_rate": "18.00",
        "cess_rate": "0.00",
    }


def test_manual_sales_invoice_uses_default_branch_and_auto_saves_customer_and_product(
    client,
    auth_headers,
    staff_user,
    branch,
    db_session,
):
    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json={
            "buyer": {
                "name": "Fresh Vendor",
                "gstin": "36ABCDE1234F1Z5",
                "pan": "ABCDE1234F",
                "email": "fresh.vendor@example.com",
                "phone": "9876543210",
                "billing_address": _manual_address("36"),
                "shipping_address": _manual_address("36"),
            },
            "invoice_date": "2026-08-30",
            "invoice_number_suffix": "MANUAL-001",
            "place_of_supply_state_code": "36",
            "payment_terms": "7 days",
            "lines": [_manual_line()],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["branch_id"] == branch.id
    assert body["buyer_name"] == "Fresh Vendor"
    assert body["buyer_customer_id"] is not None
    assert body["lines"][0]["product_id"] is not None
    assert body["lines"][0]["product_name"] == "Caustic Soda Flakes"
    assert body["final_total"] == "1180.00"

    customer_names = set(db_session.scalars(select(Customer.name)))
    product_names = set(db_session.scalars(select(Product.name)))
    assert "Fresh Vendor" in customer_names
    assert "Caustic Soda Flakes" in product_names


def test_saved_sales_invoice_can_be_created_without_exposing_branch_id(
    client,
    auth_headers,
    staff_user,
    branch,
):
    customer_response = client.post(
        "/api/v1/customers",
        headers=auth_headers(staff_user),
        json={
            "branch_id": branch.id,
            "name": "Saved Vendor",
            "billing_address": _manual_address("36"),
            "shipping_address": _manual_address("36"),
            "is_active": True,
        },
    )
    product_response = client.post(
        "/api/v1/products",
        headers=auth_headers(staff_user),
        json={
            "branch_id": branch.id,
            "name": "Saved Product",
            "description": "Product chosen from saved master",
            "hsn_sac": "29181590",
            "unit": "KG",
            "base_rate": "30.00",
            "gst_rate": "18.00",
            "cess_rate": "0.00",
            "is_active": True,
        },
    )

    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json={
            "buyer_customer_id": customer_response.json()["id"],
            "invoice_date": "2026-08-30",
            "invoice_number_suffix": "MANUAL-001",
            "place_of_supply_state_code": "36",
            "lines": [
                {
                    "product_id": product_response.json()["id"],
                    "quantity": "2.000",
                    "other_charge": "0.00",
                    "discount_amount": "0.00",
                }
            ],
        },
    )

    assert customer_response.status_code == 201
    assert product_response.status_code == 201
    assert response.status_code == 201
    assert response.json()["branch_id"] == branch.id
    assert response.json()["buyer_name"] == "Saved Vendor"
    assert response.json()["lines"][0]["product_name"] == "Saved Product"


def test_manual_reagent_line_saves_manufacturer_and_canonical_unit_snapshots(
    client, auth_headers, staff_user, manager_user, branch, db_session
):
    manufacturer = client.post(
        "/api/v1/manufacturers",
        headers=auth_headers(staff_user),
        json={"branch_id": branch.id, "code": "mrk", "name": "Merck", "is_active": True},
    )
    assert manufacturer.status_code == 201

    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json={
            "document_type": "reagent",
            "buyer": {"name": "Research Lab", "billing_address": _manual_address()},
            "invoice_date": "2026-09-25",
            "invoice_number_suffix": "REAGENT-001",
            "place_of_supply_state_code": "36",
            "lines": [{
                "product_name": "Reagent X",
                "description": "High-purity reagent",
                "manufacturer_id": manufacturer.json()["id"],
                "manufacturer_product_code": "mrk-rx-10",
                "hsn_sac": "29181590",
                "quantity": "1.250",
                "unit": "μg",
                "rate": "100.0000",
                "gst_rate": "18.00",
            }],
        },
    )

    assert response.status_code == 201, response.text
    line = response.json()["lines"][0]
    assert line["manufacturer_name"] == "Merck"
    assert line["manufacturer_code"] == "MRK"
    assert line["manufacturer_product_code"] == "MRK-RX-10"
    assert line["part_no"] == "MRK-RX-10"
    assert line["unit"] == "µg"
    saved_product = db_session.scalar(select(Product).where(Product.name == "Reagent X"))
    assert saved_product is not None
    assert saved_product.manufacturer_id is None
    assert saved_product.manufacturer_product_code is None
    assert saved_product.unit == "kg"
    assert str(saved_product.base_rate) == "0.0000"
    revision = db_session.scalar(select(InvoiceRevision).where(InvoiceRevision.invoice_id == response.json()["id"]))
    assert revision is not None
    assert revision.snapshot["lines"][0]["manufacturer_code"] == "MRK"

    client.patch(
        f"/api/v1/manufacturers/{manufacturer.json()['id']}",
        headers=auth_headers(staff_user),
        json={"code": "MRC", "name": "Merck Updated"},
    )
    historical_invoice = client.get(f"/api/v1/invoices/{response.json()['id']}", headers=auth_headers(staff_user))
    assert historical_invoice.status_code == 200
    assert historical_invoice.json()["lines"][0]["manufacturer_code"] == "MRK"
    assert historical_invoice.json()["lines"][0]["manufacturer_name"] == "Merck"
    assert revision.snapshot["lines"][0]["manufacturer_name"] == "Merck"

    submitted = client.post(
        f"/api/v1/invoices/{response.json()['id']}/submit",
        headers=auth_headers(staff_user),
    )
    assert submitted.status_code == 200, submitted.text
    approved = client.post(
        f"/api/v1/invoices/{response.json()['id']}/approve",
        headers=auth_headers(manager_user),
    )
    assert approved.status_code == 200, approved.text
    approved_line = approved.json()["lines"][0]
    assert approved_line["manufacturer_name"] == "Merck"
    assert approved_line["manufacturer_code"] == "MRK"
    assert approved_line["manufacturer_product_code"] == "MRK-RX-10"
    assert approved_line["part_no"] == "MRK-RX-10"


def test_reagent_saved_product_and_manufacturer_are_independent(
    client, auth_headers, staff_user, branch
):
    catalog_manufacturer = client.post(
        "/api/v1/manufacturers",
        headers=auth_headers(staff_user),
        json={"branch_id": branch.id, "code": "SIG", "name": "Sigma", "is_active": True},
    ).json()
    selected_manufacturer = client.post(
        "/api/v1/manufacturers",
        headers=auth_headers(staff_user),
        json={"branch_id": branch.id, "code": "MRK", "name": "Merck", "is_active": True},
    ).json()
    product = client.post(
        "/api/v1/products",
        headers=auth_headers(staff_user),
        json={
            "branch_id": branch.id,
            "manufacturer_id": catalog_manufacturer["id"],
            "manufacturer_product_code": "SIG-001",
            "name": "Shared Reagent",
            "description": "A reusable product catalog entry",
            "hsn_sac": "29181590",
            "unit": "g",
            "base_rate": "10.0000",
            "gst_rate": "18.00",
            "cess_rate": "0.00",
        },
    )

    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json={
            "document_type": "reagent",
            "buyer": {"name": "Research Lab", "billing_address": _manual_address()},
            "invoice_date": "2026-09-25",
            "invoice_number_suffix": "REAGENT-001",
            "place_of_supply_state_code": "36",
            "lines": [{
                "product_id": product.json()["id"],
                "manufacturer_id": selected_manufacturer["id"],
                "manufacturer_product_code": "MRK-001",
                "quantity": "1.000",
                "unit": "g",
                "rate": "25.0000",
                "gst_rate": "18.00",
            }],
        },
    )

    assert product.status_code == 201
    assert response.status_code == 201, response.text
    line = response.json()["lines"][0]
    assert line["manufacturer_code"] == "MRK"
    assert line["manufacturer_product_code"] == "MRK-001"
    assert line["product_name"] == "Shared Reagent"


def test_reagent_bill_requires_active_manufacturer_and_supported_unit(client, auth_headers, staff_user, branch):
    manufacturer = client.post(
        "/api/v1/manufacturers",
        headers=auth_headers(staff_user),
        json={"branch_id": branch.id, "code": "SIG", "name": "Sigma", "is_active": True},
    ).json()
    payload = {
        "document_type": "reagent",
        "buyer": {"name": "Research Lab", "billing_address": _manual_address()},
        "invoice_date": "2026-09-25",
        "invoice_number_suffix": "REAGENT-001",
        "place_of_supply_state_code": "36",
        "lines": [{
            "product_name": "Reagent Y",
            "description": "Reference material",
            "manufacturer_id": manufacturer["id"],
            "hsn_sac": "29181590",
            "quantity": "1.000",
            "unit": "gallon",
            "rate": "10.00",
            "gst_rate": "18.00",
        }],
    }
    unsupported_unit = client.post("/api/v1/invoices/preview", headers=auth_headers(staff_user), json=payload)
    payload["lines"][0]["unit"] = "g"
    client.patch(
        f"/api/v1/manufacturers/{manufacturer['id']}",
        headers=auth_headers(staff_user),
        json={"is_active": False},
    )
    inactive_manufacturer = client.post("/api/v1/invoices/preview", headers=auth_headers(staff_user), json=payload)

    assert unsupported_unit.status_code == 422
    assert inactive_manufacturer.status_code == 422


def test_purchase_orders_are_stored_separately_from_sales_invoices(
    client,
    auth_headers,
    staff_user,
    branch,
):
    response = client.post(
        "/api/v1/purchase-orders",
        headers=auth_headers(staff_user),
        json={
            "supplier": {
                "name": "Raw Material Provider",
                "gstin": "36FGHIJ1234K1Z5",
                "pan": "FGHIJ1234K",
                "email": "supplier@example.com",
                "phone": "9000000000",
                "address": _manual_address("36"),
            },
            "order_date": "2026-08-30",
            "payment_terms": "Advance before dispatch",
            "lines": [_manual_line("Sodium Hydroxide Lye")],
        },
    )
    purchase_orders = client.get("/api/v1/purchase-orders", headers=auth_headers(staff_user))
    suppliers = client.get("/api/v1/suppliers", headers=auth_headers(staff_user))
    invoices = client.get("/api/v1/invoices", headers=auth_headers(staff_user))

    assert response.status_code == 201
    body = response.json()
    assert body["branch_id"] == branch.id
    assert body["supplier_name"] == "Raw Material Provider"
    assert body["purchase_order_number"].startswith("PO-")
    assert body["final_total"] == "1180.00"
    assert [item["id"] for item in purchase_orders.json()] == [body["id"]]
    assert suppliers.json()[0]["name"] == "Raw Material Provider"
    assert invoices.json() == []


def test_saved_purchase_order_can_generate_previewable_downloadable_pdf(
    client,
    auth_headers,
    staff_user,
    tmp_path,
    monkeypatch,
):
    response = client.post(
        "/api/v1/purchase-orders",
        headers=auth_headers(staff_user),
        json={
            "supplier": {
                "name": "PDF Supplier",
                "address": _manual_address("36"),
            },
            "order_date": "2026-08-30",
            "lines": [_manual_line("PDF Material")],
        },
    )
    assert response.status_code == 201
    purchase_order_id = response.json()["id"]
    pdf_bytes = b"%PDF-1.7 purchase-order-fixture"
    monkeypatch.setattr(
        purchase_orders,
        "render_purchase_order_pdf",
        lambda context: SimpleNamespace(
            pdf_bytes=pdf_bytes,
            sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        ),
        raising=False,
    )
    monkeypatch.setattr(
        purchase_orders,
        "get_settings",
        lambda: SimpleNamespace(pdf_storage_dir=str(tmp_path)),
        raising=False,
    )

    generated = client.post(
        f"/api/v1/purchase-orders/{purchase_order_id}/generate-pdf",
        headers=auth_headers(staff_user),
    )
    duplicate = client.post(
        f"/api/v1/purchase-orders/{purchase_order_id}/generate-pdf",
        headers=auth_headers(staff_user),
    )
    download = client.get(
        f"/api/v1/purchase-orders/{purchase_order_id}/pdf",
        headers=auth_headers(staff_user),
    )

    assert generated.status_code == 200
    assert generated.json()["pdf_sha256"] == hashlib.sha256(pdf_bytes).hexdigest()
    assert generated.json()["pdf_template_version"] == "a4-purchase-order-v6"
    assert duplicate.status_code == 200
    assert duplicate.json()["pdf_sha256"] == generated.json()["pdf_sha256"]
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content == pdf_bytes
