from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy import func, select

from app.api.v1 import invoices
from app.models.invoice import Invoice, InvoiceAuditLog


def _customer_payload(branch_id: int, state_code: str = "36", name: str = "Apex Laboratories"):
    return {
        "branch_id": branch_id,
        "name": name,
        "gstin": f"{state_code}ABCDE1234F1Z5",
        "pan": "ABCDE1234F",
        "email": "billing@apex.example",
        "phone": "9876543210",
        "billing_address": {
            "name": f"{name} Billing",
            "address_line1": "Billing Street 1",
            "address_line2": "Industrial Area",
            "city": "Hyderabad",
            "state": "Telangana" if state_code == "36" else "Karnataka",
            "state_code": state_code,
            "postal_code": "500001",
        },
        "shipping_address": {
            "name": f"{name} Consignee",
            "address_line1": "Shipping Street 2",
            "address_line2": "Warehouse Block",
            "city": "Hyderabad",
            "state": "Telangana" if state_code == "36" else "Karnataka",
            "state_code": state_code,
            "postal_code": "500002",
        },
        "is_active": True,
    }


def _product_payload(branch_id: int, name: str = "Sodium Citrate"):
    return {
        "branch_id": branch_id,
        "name": name,
        "description": "Tri-sodium citrate dihydrate",
        "hsn_sac": "29181590",
        "unit": "KG",
        "base_rate": "30.00",
        "gst_rate": "18.00",
        "cess_rate": "0.00",
        "is_active": True,
    }


def _create_customer(client, auth_headers, user, branch, state_code: str = "36", name: str = "Apex Laboratories"):
    response = client.post(
        "/api/v1/customers",
        headers=auth_headers(user),
        json=_customer_payload(branch.id, state_code, name),
    )
    assert response.status_code == 201
    return response.json()


def _create_product(client, auth_headers, user, branch, name: str = "Sodium Citrate"):
    response = client.post(
        "/api/v1/products",
        headers=auth_headers(user),
        json=_product_payload(branch.id, name),
    )
    assert response.status_code == 201
    return response.json()


def _invoice_payload(branch, customer_id: int, product_id: int, place_of_supply_state_code: str = "36"):
    return {
        "branch_id": branch.id,
        "buyer_customer_id": customer_id,
        "consignee_customer_id": customer_id,
        "invoice_date": "2026-08-25",
        "delivery_note_date": "2026-08-26",
        "place_of_supply_state_code": place_of_supply_state_code,
        "po_number": "PO-2026-144",
        "po_date": "2026-08-20",
        "payment_terms": "30 days",
        "due_date": "2026-09-24",
        "transport_mode": "Road",
        "vehicle_number": "TS09AB1234",
        "lr_number": "LR-44",
        "lr_date": "2026-08-24",
        "freight_charges": "0.00",
        "packing_charges": "0.00",
        "other_charges": "0.00",
        "discount_amount": "0.00",
        "lines": [
            {
                "product_id": product_id,
                "description": "Sodium Citrate BP",
                "hsn_sac": "29181590",
                "quantity": "9798.000",
                "unit": "KG",
                "rate": "30.00",
                "discount_amount": "0.00",
                "gst_rate": "18.00",
                "cess_rate": "0.00",
            }
        ],
    }


def _create_invoice(client, auth_headers, user, branch, customer_id: int, product_id: int, place_of_supply_state_code: str = "36"):
    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(user),
        json=_invoice_payload(branch, customer_id, product_id, place_of_supply_state_code),
    )
    assert response.status_code == 201
    return response.json()


def test_invoice_preview_and_draft_creation_return_backend_authoritative_totals(
    client, auth_headers, staff_user, branch, db_session
):
    branch.bank_name = "ICICI Bank"
    branch.bank_branch_name = "Gurugram Sector Forty Four"
    branch.bank_account_name = "Pristine Biopharma"
    branch.bank_account_number = "777705889826"
    branch.bank_ifsc_code = "ICIC0005961"
    branch.terms_body = "Insurance at seller's account.\nPayment by bank transfer only."
    customer = _create_customer(client, auth_headers, staff_user, branch)
    product = _create_product(client, auth_headers, staff_user, branch)
    payload = _invoice_payload(branch, customer["id"], product["id"])

    preview_response = client.post(
        "/api/v1/invoices/preview",
        headers=auth_headers(staff_user),
        json=payload,
    )
    create_response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json=payload,
    )

    assert preview_response.status_code == 200
    assert preview_response.json()["final_total"] == "346849.00"
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["status"] == "draft"
    assert body["invoice_number"] is None
    assert body["delivery_note_date"] == "2026-08-26"
    assert body["taxable_value"] == "293940.00"
    assert body["cgst_amount"] == "26454.60"
    assert body["sgst_amount"] == "26454.60"
    assert body["final_total"] == "346849.00"
    assert body["amount_in_words"] == "Rupees Three Lakh Forty Six Thousand Eight Hundred Forty Nine Only"
    invoice = db_session.get(Invoice, body["id"])
    assert invoice is not None
    assert invoice.bank_account_number == "777705889826"
    assert invoice.bank_ifsc_code == "ICIC0005961"
    assert invoice.terms_body == "Insurance at seller's account.\nPayment by bank transfer only."


def test_manual_invoice_preserves_separate_consignee_snapshot(
    client, auth_headers, staff_user, branch
):
    product = _create_product(client, auth_headers, staff_user, branch)
    buyer = _customer_payload(branch.id, name="Buyer Labs")
    consignee = _customer_payload(branch.id, name="Delivery Warehouse")
    consignee["gstin"] = buyer["gstin"]
    consignee["pan"] = "BBBBB0000B"
    payload = _invoice_payload(branch, 0, product["id"])
    payload.pop("buyer_customer_id")
    payload.pop("consignee_customer_id")
    payload["buyer"] = buyer
    payload["consignee"] = consignee

    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json=payload,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["buyer_customer_id"] != body["consignee_customer_id"]
    assert body["consignee_name"] == "Delivery Warehouse Consignee"
    assert body["consignee_gstin"] == buyer["gstin"]
    assert body["consignee_address_line1"] == "Shipping Street 2"


def test_saved_buyer_allows_manual_consignee_with_shared_gstin_and_address(
    client, auth_headers, staff_user, branch
):
    buyer = _create_customer(client, auth_headers, staff_user, branch, name="Saved Buyer")
    product = _create_product(client, auth_headers, staff_user, branch)
    consignee = _customer_payload(branch.id, name="Saved Delivery Warehouse")
    consignee["gstin"] = buyer["gstin"]
    consignee["pan"] = "BBBBB0000B"
    payload = _invoice_payload(branch, buyer["id"], product["id"])
    payload.pop("consignee_customer_id")
    payload["consignee"] = consignee

    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json=payload,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["buyer_customer_id"] == buyer["id"]
    assert body["buyer_customer_id"] != body["consignee_customer_id"]
    assert body["consignee_name"] == "Saved Delivery Warehouse Consignee"
    assert body["consignee_gstin"] == buyer["gstin"]
    assert body["consignee_address_line1"] == "Shipping Street 2"


def test_staff_can_submit_manager_can_approve_and_approved_invoice_is_immutable(
    client, auth_headers, staff_user, manager_user, branch, db_session
):
    customer = _create_customer(client, auth_headers, staff_user, branch)
    product = _create_product(client, auth_headers, staff_user, branch)
    invoice = _create_invoice(client, auth_headers, staff_user, branch, customer["id"], product["id"])

    submit_response = client.post(
        f"/api/v1/invoices/{invoice['id']}/submit",
        headers=auth_headers(staff_user),
    )
    duplicate_submit_response = client.post(
        f"/api/v1/invoices/{invoice['id']}/submit",
        headers=auth_headers(staff_user),
    )
    approve_response = client.post(
        f"/api/v1/invoices/{invoice['id']}/approve",
        headers=auth_headers(manager_user),
    )
    duplicate_approve_response = client.post(
        f"/api/v1/invoices/{invoice['id']}/approve",
        headers=auth_headers(manager_user),
    )
    patch_response = client.patch(
        f"/api/v1/invoices/{invoice['id']}",
        headers=auth_headers(staff_user),
        json={"payment_terms": "Changed after approval"},
    )

    assert submit_response.status_code == 200
    assert submit_response.json()["status"] == "pending_approval"
    assert duplicate_submit_response.status_code == 200
    assert approve_response.status_code == 200
    approved = approve_response.json()
    assert approved["status"] == "approved"
    assert approved["invoice_number"] == "PBPL/2026-27/NO. 00001"
    assert duplicate_approve_response.status_code == 200
    assert duplicate_approve_response.json()["invoice_number"] == approved["invoice_number"]
    assert patch_response.status_code == 409
    assert db_session.scalar(select(func.count()).select_from(InvoiceAuditLog)) == 2

    stored_invoice = db_session.get(Invoice, invoice["id"])
    assert stored_invoice.final_total == Decimal("346849.00")


def test_staff_cannot_approve_and_unassigned_branch_access_is_denied(
    client, auth_headers, admin_user, manager_user, staff_user, branch, other_branch
):
    customer = _create_customer(client, auth_headers, admin_user, other_branch, "29", "Other Buyer")
    product = _create_product(client, auth_headers, admin_user, other_branch, "Other Product")

    create_response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json=_invoice_payload(other_branch, customer["id"], product["id"], "29"),
    )
    admin_invoice = _create_invoice(client, auth_headers, admin_user, other_branch, customer["id"], product["id"], "29")
    approve_response = client.post(
        f"/api/v1/invoices/{admin_invoice['id']}/approve",
        headers=auth_headers(staff_user),
    )
    manager_read_response = client.get(
        f"/api/v1/invoices/{admin_invoice['id']}",
        headers=auth_headers(manager_user),
    )

    assert create_response.status_code == 403
    assert approve_response.status_code == 403
    assert manager_read_response.status_code == 403


def test_invoice_numbers_are_company_and_financial_year_scoped(
    client, auth_headers, admin_user, branch, other_branch
):
    customer = _create_customer(client, auth_headers, admin_user, branch)
    product = _create_product(client, auth_headers, admin_user, branch)
    other_customer = _create_customer(client, auth_headers, admin_user, other_branch, "29", "Other Buyer")
    other_product = _create_product(client, auth_headers, admin_user, other_branch, "Other Product")

    first = _create_invoice(client, auth_headers, admin_user, branch, customer["id"], product["id"])
    second = _create_invoice(client, auth_headers, admin_user, branch, customer["id"], product["id"])
    other = _create_invoice(client, auth_headers, admin_user, other_branch, other_customer["id"], other_product["id"], "29")

    for invoice in [first, second, other]:
        submit = client.post(f"/api/v1/invoices/{invoice['id']}/submit", headers=auth_headers(admin_user))
        assert submit.status_code == 200

    first_approved = client.post(f"/api/v1/invoices/{first['id']}/approve", headers=auth_headers(admin_user)).json()
    second_approved = client.post(f"/api/v1/invoices/{second['id']}/approve", headers=auth_headers(admin_user)).json()
    other_approved = client.post(f"/api/v1/invoices/{other['id']}/approve", headers=auth_headers(admin_user)).json()

    assert first_approved["invoice_number"] == "PBPL/2026-27/NO. 00001"
    assert second_approved["invoice_number"] == "PBPL/2026-27/NO. 00002"
    assert other_approved["invoice_number"] == "PBPL/2026-27/NO. 00003"


def test_pdf_generated_status_transition_is_recorded(
    client, auth_headers, admin_user, branch, db_session, monkeypatch, tmp_path
):
    customer = _create_customer(client, auth_headers, admin_user, branch)
    product = _create_product(client, auth_headers, admin_user, branch)
    invoice = _create_invoice(client, auth_headers, admin_user, branch, customer["id"], product["id"])
    submit = client.post(f"/api/v1/invoices/{invoice['id']}/submit", headers=auth_headers(admin_user))
    approve = client.post(f"/api/v1/invoices/{invoice['id']}/approve", headers=auth_headers(admin_user))
    monkeypatch.setattr(invoices, "get_settings", lambda: SimpleNamespace(pdf_storage_dir=str(tmp_path)))

    pdf_response = client.post(
        f"/api/v1/invoices/{invoice['id']}/mark-pdf-generated",
        headers=auth_headers(admin_user),
    )

    assert submit.status_code == 200
    assert approve.status_code == 200
    assert pdf_response.status_code == 200
    assert pdf_response.json()["status"] == "pdf_generated"
    assert pdf_response.json()["pdf_template_version"] == "a4-invoice-v1"
    assert len(pdf_response.json()["pdf_sha256"]) == 64
    assert db_session.scalar(select(func.count()).select_from(InvoiceAuditLog)) == 3


def test_invoice_number_counter_uses_postgresql_advisory_transaction_lock():
    db = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        execute=Mock(),
    )

    invoices._lock_counter(db, branch_id=7, financial_year="2026-27")

    statement = db.execute.call_args.args[0]
    assert "pg_advisory_xact_lock" in str(statement)
    assert "key" in db.execute.call_args.args[1]


def test_approved_invoice_generates_downloadable_pdf_and_persists_metadata(
    client,
    auth_headers,
    admin_user,
    branch,
    db_session,
    monkeypatch,
    tmp_path,
):
    customer = _create_customer(client, auth_headers, admin_user, branch)
    product = _create_product(client, auth_headers, admin_user, branch)
    invoice = _create_invoice(client, auth_headers, admin_user, branch, customer["id"], product["id"])
    assert client.post(f"/api/v1/invoices/{invoice['id']}/submit", headers=auth_headers(admin_user)).status_code == 200
    assert client.post(f"/api/v1/invoices/{invoice['id']}/approve", headers=auth_headers(admin_user)).status_code == 200
    monkeypatch.setattr(invoices, "get_settings", lambda: SimpleNamespace(pdf_storage_dir=str(tmp_path)))

    generated = client.post(
        f"/api/v1/invoices/{invoice['id']}/generate-pdf",
        headers=auth_headers(admin_user),
    )
    duplicate = client.post(
        f"/api/v1/invoices/{invoice['id']}/generate-pdf",
        headers=auth_headers(admin_user),
    )
    download = client.get(
        f"/api/v1/invoices/{invoice['id']}/pdf",
        headers=auth_headers(admin_user),
    )

    assert generated.status_code == 200
    body = generated.json()
    assert body["status"] == "pdf_generated"
    assert body["pdf_template_version"] == "a4-invoice-v1"
    assert len(body["pdf_sha256"]) == 64
    assert body["pdf_storage_key"].endswith(".pdf")
    assert duplicate.status_code == 200
    assert duplicate.json()["pdf_sha256"] == body["pdf_sha256"]
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF")
    assert (tmp_path / body["pdf_storage_key"]).is_file()
    assert db_session.scalar(select(func.count()).select_from(InvoiceAuditLog)) == 3


def test_pdf_generation_is_rejected_until_invoice_is_approved(
    client,
    auth_headers,
    admin_user,
    branch,
    monkeypatch,
    tmp_path,
):
    customer = _create_customer(client, auth_headers, admin_user, branch)
    product = _create_product(client, auth_headers, admin_user, branch)
    invoice = _create_invoice(client, auth_headers, admin_user, branch, customer["id"], product["id"])
    monkeypatch.setattr(invoices, "get_settings", lambda: SimpleNamespace(pdf_storage_dir=str(tmp_path)))

    response = client.post(
        f"/api/v1/invoices/{invoice['id']}/generate-pdf",
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 409
