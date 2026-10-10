from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from sqlalchemy import func, select

from app.api.v1 import invoices
from app.models.invoice import Invoice, InvoiceAuditLog
from app.services.invoice_pdf import TEMPLATE_VERSION


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


def _invoice_payload(
    branch,
    customer_id: int,
    product_id: int,
    place_of_supply_state_code: str = "36",
    invoice_number_suffix: str | None = None,
):
    return {
        "branch_id": branch.id,
        "buyer_customer_id": customer_id,
        "consignee_customer_id": customer_id,
        "invoice_date": "2026-08-25",
        "invoice_number_suffix": invoice_number_suffix or uuid4().hex[:10].upper(),
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


def _create_invoice(
    client,
    auth_headers,
    user,
    branch,
    customer_id: int,
    product_id: int,
    place_of_supply_state_code: str = "36",
    invoice_number_suffix: str | None = None,
):
    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(user),
        json=_invoice_payload(
            branch,
            customer_id,
            product_id,
            place_of_supply_state_code,
            invoice_number_suffix,
        ),
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
    assert body["invoice_number"] == f"PBPL/2026-27/{payload['invoice_number_suffix']}"
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


def test_staff_entered_invoice_number_is_saved_with_the_financial_year_prefix(
    client, auth_headers, staff_user, branch
):
    customer = _create_customer(client, auth_headers, staff_user, branch)
    product = _create_product(client, auth_headers, staff_user, branch)
    payload = _invoice_payload(branch, customer["id"], product["id"])

    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json={**payload, "invoice_number_suffix": "MANUAL-001"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["invoice_number"] == "PBPL/2026-27/MANUAL-001"
    assert response.json()["financial_year"] == "2026-27"


@pytest.mark.parametrize("suffix", [None, "", "   ", "BAD.NUMBER", "X" * 31])
def test_manual_invoice_number_rejects_empty_or_invalid_values(client, auth_headers, staff_user, branch, suffix):
    customer = _create_customer(client, auth_headers, staff_user, branch)
    product = _create_product(client, auth_headers, staff_user, branch)
    payload = _invoice_payload(branch, customer["id"], product["id"])
    payload["invoice_number_suffix"] = suffix
    response = client.post("/api/v1/invoices", headers=auth_headers(staff_user), json=payload)
    assert response.status_code == 422
    assert any(error["loc"][-1] == "invoice_number_suffix" for error in response.json()["detail"])


def test_preview_does_not_require_a_number_but_draft_creation_does(client, auth_headers, staff_user, branch):
    customer = _create_customer(client, auth_headers, staff_user, branch)
    product = _create_product(client, auth_headers, staff_user, branch)
    payload = _invoice_payload(branch, customer["id"], product["id"])
    payload.pop("invoice_number_suffix")
    preview = client.post("/api/v1/invoices/preview", headers=auth_headers(staff_user), json=payload)
    created = client.post("/api/v1/invoices", headers=auth_headers(staff_user), json=payload)
    assert preview.status_code == 200
    assert preview.json()["final_total"] == "346849.00"
    assert created.status_code == 422
    assert any(error["loc"][-1] == "invoice_number_suffix" for error in created.json()["detail"])


def test_sales_and_reagent_reject_shared_number_duplicates_and_replay_same_save(
    client, auth_headers, staff_user, manager_user, branch
):
    customer = _create_customer(client, auth_headers, staff_user, branch)
    product = _create_product(client, auth_headers, staff_user, branch)
    sales = _create_invoice(client, auth_headers, staff_user, branch, customer["id"], product["id"], invoice_number_suffix="SHARED-42")
    manufacturer = client.post("/api/v1/manufacturers", headers=auth_headers(staff_user), json={"branch_id": branch.id, "code": "SIG", "name": "Sigma", "is_active": True}).json()
    reagent_payload = _invoice_payload(branch, customer["id"], product["id"], invoice_number_suffix=" shared-42 ")
    reagent_payload["document_type"] = "reagent"
    reagent_payload["lines"][0]["manufacturer_id"] = manufacturer["id"]
    duplicate = client.post("/api/v1/invoices", headers=auth_headers(staff_user), json=reagent_payload)
    assert duplicate.status_code == 409
    assert "PBPL/2026-27/SHARED-42" in duplicate.json()["detail"]
    reagent_payload["invoice_number_suffix"] = " reagent-007 "
    headers = {**auth_headers(staff_user), "Idempotency-Key": "manual-reagent-007"}
    created = client.post("/api/v1/invoices", headers=headers, json=reagent_payload)
    replay = client.post("/api/v1/invoices", headers=headers, json=reagent_payload)
    assert created.status_code == 201, created.text
    assert replay.status_code == 200
    assert replay.json()["id"] == created.json()["id"]
    assert created.json()["invoice_number"] == "PBPL/2026-27/REAGENT-007"
    reverse_duplicate = client.post(
        "/api/v1/invoices", headers=auth_headers(staff_user),
        json=_invoice_payload(branch, customer["id"], product["id"], invoice_number_suffix=" reagent-007 "),
    )
    assert reverse_duplicate.status_code == 409, reverse_duplicate.text
    assert "PBPL/2026-27/REAGENT-007" in reverse_duplicate.json()["detail"]
    assert client.post(f"/api/v1/invoices/{created.json()['id']}/submit", headers=auth_headers(staff_user)).status_code == 200
    approved = client.post(f"/api/v1/invoices/{created.json()['id']}/approve", headers=auth_headers(manager_user))
    assert approved.status_code == 200
    assert approved.json()["invoice_number"] == "PBPL/2026-27/REAGENT-007"
    assert client.get(f"/api/v1/invoices/{sales['id']}", headers=auth_headers(staff_user)).json()["invoice_number"] == "PBPL/2026-27/SHARED-42"


def test_draft_number_edit_keeps_the_suffix_when_financial_year_changes_and_rejects_conflicts(
    client, auth_headers, staff_user, branch
):
    customer = _create_customer(client, auth_headers, staff_user, branch)
    product = _create_product(client, auth_headers, staff_user, branch)
    draft = _create_invoice(client, auth_headers, staff_user, branch, customer["id"], product["id"], invoice_number_suffix="EDIT-1")
    edited = client.patch(f"/api/v1/invoices/{draft['id']}", headers=auth_headers(staff_user), json={"expected_version": 1, "invoice_number_suffix": "EDIT-2", "invoice_date": "2027-04-01"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["invoice_number"] == "PBPL/2027-28/EDIT-2"
    changed_date = client.patch(f"/api/v1/invoices/{draft['id']}", headers=auth_headers(staff_user), json={"expected_version": 2, "invoice_date": "2027-03-31"})
    assert changed_date.status_code == 200
    assert changed_date.json()["invoice_number"] == "PBPL/2026-27/EDIT-2"
    _create_invoice(client, auth_headers, staff_user, branch, customer["id"], product["id"], invoice_number_suffix="TAKEN-1")
    conflict = client.patch(f"/api/v1/invoices/{draft['id']}", headers=auth_headers(staff_user), json={"expected_version": 3, "invoice_number_suffix": "TAKEN-1", "payment_terms": "Should not save"})
    assert conflict.status_code == 409
    unchanged = client.get(f"/api/v1/invoices/{draft['id']}", headers=auth_headers(staff_user)).json()
    assert unchanged["invoice_number"] == "PBPL/2026-27/EDIT-2"
    assert unchanged["payment_terms"] == "30 days"
    assert unchanged["version"] == 3
    cleared = client.patch(f"/api/v1/invoices/{draft['id']}", headers=auth_headers(staff_user), json={"invoice_number_suffix": None})
    assert cleared.status_code == 422


def test_legacy_unnumbered_draft_requires_manual_entry_before_submission(client, auth_headers, staff_user, branch, db_session):
    customer = _create_customer(client, auth_headers, staff_user, branch)
    product = _create_product(client, auth_headers, staff_user, branch)
    draft = _create_invoice(client, auth_headers, staff_user, branch, customer["id"], product["id"])
    db_session.get(Invoice, draft["id"]).invoice_number = None
    db_session.commit()
    submitted = client.post(f"/api/v1/invoices/{draft['id']}/submit", headers=auth_headers(staff_user))
    assert submitted.status_code == 422
    assert "invoice number" in submitted.json()["detail"].lower()
    patched = client.patch(f"/api/v1/invoices/{draft['id']}", headers=auth_headers(staff_user), json={"invoice_number_suffix": "LEGACY-1"})
    assert patched.status_code == 200
    assert patched.json()["invoice_number"] == "PBPL/2026-27/LEGACY-1"
    assert client.post(f"/api/v1/invoices/{draft['id']}/submit", headers=auth_headers(staff_user)).status_code == 200


def test_approved_invoice_number_uses_indian_financial_year_from_invoice_date(
    client, auth_headers, staff_user, manager_user, branch
):
    customer = _create_customer(client, auth_headers, staff_user, branch)
    product = _create_product(client, auth_headers, staff_user, branch)
    march_payload = _invoice_payload(
        branch,
        customer["id"],
        product["id"],
    )
    march_payload["invoice_date"] = "2027-03-31"
    march_payload["invoice_number_suffix"] = "00001"
    april_payload = _invoice_payload(
        branch,
        customer["id"],
        product["id"],
    )
    april_payload["invoice_date"] = "2027-04-01"
    april_payload["invoice_number_suffix"] = "00001"

    march_invoice = client.post(
        "/api/v1/invoices", headers=auth_headers(staff_user), json=march_payload
    )
    april_invoice = client.post(
        "/api/v1/invoices", headers=auth_headers(staff_user), json=april_payload
    )

    assert march_invoice.status_code == 201, march_invoice.text
    assert april_invoice.status_code == 201, april_invoice.text
    march_submit = client.post(
        f"/api/v1/invoices/{march_invoice.json()['id']}/submit",
        headers=auth_headers(staff_user),
    )
    april_submit = client.post(
        f"/api/v1/invoices/{april_invoice.json()['id']}/submit",
        headers=auth_headers(staff_user),
    )
    march_approved = client.post(
        f"/api/v1/invoices/{march_invoice.json()['id']}/approve",
        headers=auth_headers(manager_user),
    )
    april_approved = client.post(
        f"/api/v1/invoices/{april_invoice.json()['id']}/approve",
        headers=auth_headers(manager_user),
    )

    assert march_submit.status_code == april_submit.status_code == 200
    assert march_approved.json()["invoice_number"] == "PBPL/2026-27/00001"
    assert march_approved.json()["financial_year"] == "2026-27"
    assert april_approved.json()["invoice_number"] == "PBPL/2027-28/00001"
    assert april_approved.json()["financial_year"] == "2027-28"


def test_reagent_bill_persists_its_type_and_line_fields_and_has_separate_register(
    client, auth_headers, staff_user, manager_user, branch
):
    customer = _create_customer(client, auth_headers, staff_user, branch)
    manufacturer = client.post(
        "/api/v1/manufacturers",
        headers=auth_headers(staff_user),
        json={"branch_id": branch.id, "code": "SIG", "name": "Sigma", "is_active": True},
    ).json()
    product_response = client.post(
        "/api/v1/products",
        headers=auth_headers(staff_user),
        json={
            **_product_payload(branch.id, "Laboratory Reagent"),
            "manufacturer_id": manufacturer["id"],
            "manufacturer_product_code": "RX-001",
        },
    )
    assert product_response.status_code == 201, product_response.text
    product = product_response.json()
    payload = _invoice_payload(branch, customer["id"], product["id"])
    payload["document_type"] = "reagent"
    payload["lines"][0].update(
        {
            "description": "Analytical grade reagent",
            "manufacturer_id": manufacturer["id"],
            "manufacturer_product_code": "RX-001",
            "part_no": "RX-001",
            "discount_amount": "0.00",
            "discount_percent": "12.50",
        }
    )

    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json=payload,
    )

    assert response.status_code == 201, response.text
    bill = response.json()
    assert bill["document_type"] == "reagent"
    assert bill["lines"][0]["part_no"] == "RX-001"
    assert bill["lines"][0]["manufacturer_name"] == "Sigma"
    assert bill["lines"][0]["manufacturer_code"] == "SIG"
    assert bill["lines"][0]["manufacturer_product_code"] == "RX-001"
    assert bill["lines"][0]["discount_percent"] == "12.50"
    assert bill["lines"][0]["discount_amount"] == "36742.50"
    assert bill["lines"][0]["taxable_value"] == "257197.50"

    submitted = client.post(
        f"/api/v1/invoices/{bill['id']}/submit",
        headers=auth_headers(staff_user),
    )
    assert submitted.status_code == 200
    approved = client.post(
        f"/api/v1/invoices/{bill['id']}/approve",
        headers=auth_headers(manager_user),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["lines"][0]["discount_amount"] == "36742.50"
    assert approved.json()["taxable_value"] == "257197.50"

    assert client.get("/api/v1/invoices", headers=auth_headers(staff_user)).json() == []
    reagent_register = client.get(
        "/api/v1/invoices?document_type=reagent",
        headers=auth_headers(staff_user),
    )
    assert reagent_register.status_code == 200
    assert [item["id"] for item in reagent_register.json()] == [bill["id"]]


def test_sales_and_reagent_share_manual_number_namespace_but_keep_separate_register_counts(
    client, auth_headers, staff_user, manager_user, branch
):
    customer = _create_customer(client, auth_headers, staff_user, branch)
    product = _create_product(client, auth_headers, staff_user, branch)
    manufacturer_response = client.post(
        "/api/v1/manufacturers",
        headers=auth_headers(staff_user),
        json={"branch_id": branch.id, "code": "SEQ", "name": "Sequence Manufacturer", "is_active": True},
    )
    assert manufacturer_response.status_code == 201, manufacturer_response.text

    drafts = []
    for sequence, document_type in enumerate(("sales", "reagent", "sales"), start=1):
        payload = _invoice_payload(branch, customer["id"], product["id"])
        payload["document_type"] = document_type
        payload["invoice_number_suffix"] = f"{sequence:05d}"
        if document_type == "reagent":
            payload["lines"][0]["manufacturer_id"] = manufacturer_response.json()["id"]
        created = client.post("/api/v1/invoices", headers=auth_headers(staff_user), json=payload)
        assert created.status_code == 201, created.text
        assert created.json()["invoice_number"] == f"PBPL/2026-27/{sequence:05d}"
        drafts.append(created.json())

    approved = []
    for draft in drafts:
        submitted = client.post(
            f"/api/v1/invoices/{draft['id']}/submit",
            headers=auth_headers(staff_user),
            json={"expected_version": draft["version"]},
        )
        assert submitted.status_code == 200, submitted.text
        response = client.post(
            f"/api/v1/invoices/{draft['id']}/approve",
            headers=auth_headers(manager_user),
            json={"expected_version": submitted.json()["version"]},
        )
        assert response.status_code == 200, response.text
        approved.append(response.json())

    assert [item["invoice_number"] for item in approved] == [
        "PBPL/2026-27/00001",
        "PBPL/2026-27/00002",
        "PBPL/2026-27/00003",
    ]

    sales_register = client.get("/api/v1/invoices/register?document_type=sales", headers=auth_headers(staff_user))
    reagent_register = client.get("/api/v1/invoices/register?document_type=reagent", headers=auth_headers(staff_user))
    dashboard = client.get("/api/v1/dashboard", headers=auth_headers(staff_user))
    assert sales_register.status_code == 200
    assert reagent_register.status_code == 200
    assert sales_register.json()["total"] == 2
    assert reagent_register.json()["total"] == 1
    assert dashboard.status_code == 200
    assert dashboard.json()["sales_invoice_count"] == 2
    assert dashboard.json()["reagent_invoice_count"] == 1


def test_manual_numbering_preserves_historical_numbers_and_does_not_allocate_a_sequence(
    client, auth_headers, staff_user, manager_user, branch, db_session
):
    customer = _create_customer(client, auth_headers, staff_user, branch)
    product = _create_product(client, auth_headers, staff_user, branch)
    historical = _create_invoice(client, auth_headers, staff_user, branch, customer["id"], product["id"])
    stored_historical = db_session.get(Invoice, historical["id"])
    stored_historical.invoice_number = "PBPL/2026-27/NO. 00001"
    stored_historical.financial_year = "2026-27"
    db_session.commit()

    submitted = client.post(
        f"/api/v1/invoices/{historical['id']}/submit",
        headers=auth_headers(staff_user),
    )
    approved_historical = client.post(
        f"/api/v1/invoices/{historical['id']}/approve",
        headers=auth_headers(manager_user),
    )
    fresh = _create_invoice(client, auth_headers, staff_user, branch, customer["id"], product["id"], invoice_number_suffix="MANUAL-009")
    fresh_submitted = client.post(
        f"/api/v1/invoices/{fresh['id']}/submit",
        headers=auth_headers(staff_user),
    )
    fresh_approved = client.post(
        f"/api/v1/invoices/{fresh['id']}/approve",
        headers=auth_headers(manager_user),
    )

    assert submitted.status_code == 200
    assert approved_historical.json()["invoice_number"] == "PBPL/2026-27/NO. 00001"
    assert fresh_submitted.status_code == 200
    assert fresh_approved.status_code == 200, fresh_approved.text
    assert fresh_approved.json()["invoice_number"] == "PBPL/2026-27/MANUAL-009"
    assert fresh_approved.json()["invoice_sequence"] is None


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
    assert approved["invoice_number"] == invoice["invoice_number"]
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


def test_manual_invoice_numbers_are_unique_across_branches(
    client, auth_headers, admin_user, manager_user, branch, other_branch, db_session
):
    from app.models.user import UserBranchAssignment

    db_session.add(UserBranchAssignment(user_id=manager_user.id, branch_id=other_branch.id))
    db_session.commit()
    customer = _create_customer(client, auth_headers, admin_user, branch)
    product = _create_product(client, auth_headers, admin_user, branch)
    other_customer = _create_customer(client, auth_headers, admin_user, other_branch, "29", "Other Buyer")
    other_product = _create_product(client, auth_headers, admin_user, other_branch, "Other Product")

    first = _create_invoice(client, auth_headers, admin_user, branch, customer["id"], product["id"], invoice_number_suffix="00001")
    second = _create_invoice(client, auth_headers, admin_user, branch, customer["id"], product["id"], invoice_number_suffix="00002")
    other = _create_invoice(client, auth_headers, admin_user, other_branch, other_customer["id"], other_product["id"], "29", invoice_number_suffix="00003")
    duplicate = client.post("/api/v1/invoices", headers=auth_headers(admin_user), json=_invoice_payload(other_branch, other_customer["id"], other_product["id"], "29", invoice_number_suffix="00001"))
    assert duplicate.status_code == 409

    for invoice in [first, second, other]:
        submit = client.post(f"/api/v1/invoices/{invoice['id']}/submit", headers=auth_headers(admin_user))
        assert submit.status_code == 200

    first_approved = client.post(f"/api/v1/invoices/{first['id']}/approve", headers=auth_headers(manager_user)).json()
    second_approved = client.post(f"/api/v1/invoices/{second['id']}/approve", headers=auth_headers(manager_user)).json()
    other_approved = client.post(f"/api/v1/invoices/{other['id']}/approve", headers=auth_headers(manager_user)).json()

    assert first_approved["invoice_number"] == "PBPL/2026-27/00001"
    assert second_approved["invoice_number"] == "PBPL/2026-27/00002"
    assert other_approved["invoice_number"] == "PBPL/2026-27/00003"


def test_pdf_generated_status_transition_is_recorded(
    client, auth_headers, admin_user, manager_user, branch, db_session, monkeypatch, tmp_path
):
    customer = _create_customer(client, auth_headers, admin_user, branch)
    product = _create_product(client, auth_headers, admin_user, branch)
    invoice = _create_invoice(client, auth_headers, admin_user, branch, customer["id"], product["id"])
    submit = client.post(f"/api/v1/invoices/{invoice['id']}/submit", headers=auth_headers(admin_user))
    approve = client.post(f"/api/v1/invoices/{invoice['id']}/approve", headers=auth_headers(manager_user))
    monkeypatch.setattr(invoices, "get_settings", lambda: SimpleNamespace(pdf_storage_dir=str(tmp_path)))

    pdf_response = client.post(
        f"/api/v1/invoices/{invoice['id']}/mark-pdf-generated",
        headers=auth_headers(manager_user),
    )

    assert submit.status_code == 200
    assert approve.status_code == 200
    assert pdf_response.status_code == 200
    assert pdf_response.json()["status"] == "pdf_generated"
    assert pdf_response.json()["pdf_template_version"] == TEMPLATE_VERSION
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
    manager_user,
    branch,
    db_session,
    monkeypatch,
    tmp_path,
):
    customer = _create_customer(client, auth_headers, admin_user, branch)
    product = _create_product(client, auth_headers, admin_user, branch)
    invoice = _create_invoice(client, auth_headers, admin_user, branch, customer["id"], product["id"])
    assert client.post(f"/api/v1/invoices/{invoice['id']}/submit", headers=auth_headers(admin_user)).status_code == 200
    assert client.post(f"/api/v1/invoices/{invoice['id']}/approve", headers=auth_headers(manager_user)).status_code == 200
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
    assert body["pdf_template_version"] == TEMPLATE_VERSION
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
