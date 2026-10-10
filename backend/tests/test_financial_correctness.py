from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.invoice import Invoice, InvoiceCreationRequest
from app.models.master_records import Customer, Supplier
from app.models.purchase_order import PurchaseOrder, PurchaseOrderCreationRequest
from app.services.invoice_calculator import InvoiceCalculationLine, calculate_invoice


def _address(name: str, state_code: str = "36", address_line1: str = "Billing Street 1") -> dict:
    return {
        "name": name,
        "address_line1": address_line1,
        "address_line2": "Industrial Area",
        "city": "Hyderabad",
        "state": "Telangana" if state_code == "36" else "Karnataka",
        "state_code": state_code,
        "postal_code": "500001",
    }


def _customer(name: str, gstin: str, *, state_code: str = "36", address_line1: str = "Billing Street 1") -> dict:
    address = _address(f"{name} Office", state_code, address_line1)
    return {
        "name": name,
        "gstin": gstin,
        "pan": "ABCDE1234F",
        "phone": "9876543210",
        "billing_address": address,
        "shipping_address": address,
        "is_active": True,
    }


def _line(*, quantity: str = "1.000", rate: str = "100.00", discount: str = "0.00") -> dict:
    return {
        "product_name": "Chemical Material",
        "description": "Chemical Material description",
        "hsn_sac": "29181590",
        "quantity": quantity,
        "unit": "KG",
        "rate": rate,
        "other_charge": "0.00",
        "discount_amount": discount,
        "gst_rate": "18.00",
        "cess_rate": "0.00",
    }


def _invoice_payload(branch, *, buyer: dict | None = None, quantity: str = "1.000", discount: str = "0.00") -> dict:
    return {
        "branch_id": branch.id,
        "buyer": buyer or _customer("Invoice Buyer", "36ABCDE1234F1Z5"),
        "invoice_date": "2026-09-16",
        "invoice_number_suffix": uuid4().hex[:10].upper(),
        "place_of_supply_state_code": "36",
        "discount_amount": discount,
        "lines": [_line(quantity=quantity)],
    }


def _purchase_order_payload(branch, *, supplier_name: str = "PO Supplier", supplier_gstin: str = "36FGHIJ1234K1Z5") -> dict:
    return {
        "branch_id": branch.id,
        "supplier": {
            "name": supplier_name,
            "gstin": supplier_gstin,
            "pan": "FGHIJ1234K",
            "phone": "9000000000",
            "address": _address(f"{supplier_name} Office"),
            "is_active": True,
        },
        "order_date": "2026-09-16",
        "lines": [_line()],
    }


def test_calculator_rejects_quantity_beyond_persisted_precision():
    try:
        calculate_invoice(
            branch_state_code="36",
            place_of_supply_state_code="36",
            lines=[
                InvoiceCalculationLine(
                    description="Chemical Material",
                    hsn_sac="29181590",
                    quantity=Decimal("1.0004"),
                    unit="KG",
                    rate=Decimal("10000.00"),
                    discount_amount=Decimal("0.00"),
                    gst_rate=Decimal("0.00"),
                    cess_rate=Decimal("0.00"),
                )
            ],
        )
    except ValueError as exc:
        assert "quantity" in str(exc).lower()
    else:
        raise AssertionError("four-decimal quantity must be rejected before storage can round it")


def test_document_adjustments_reconcile_with_line_taxes_using_weighted_rates():
    result = calculate_invoice(
        branch_state_code="36",
        place_of_supply_state_code="36",
        lines=[
            InvoiceCalculationLine(
                description="Material A",
                hsn_sac="29181590",
                quantity=Decimal("1.000"),
                unit="KG",
                rate=Decimal("100.00"),
                discount_amount=Decimal("0.00"),
                gst_rate=Decimal("18.00"),
                cess_rate=Decimal("0.00"),
            ),
            InvoiceCalculationLine(
                description="Material B",
                hsn_sac="29181590",
                quantity=Decimal("1.000"),
                unit="KG",
                rate=Decimal("200.00"),
                discount_amount=Decimal("0.00"),
                gst_rate=Decimal("5.00"),
                cess_rate=Decimal("0.00"),
            ),
        ],
        freight_charges=Decimal("10.00"),
        discount_amount=Decimal("3.00"),
    )

    assert result.taxable_value == Decimal("307.00")
    assert result.cgst_amount == Decimal("14.33")
    assert result.sgst_amount == Decimal("14.33")
    assert result.igst_amount == Decimal("0.00")
    assert result.unrounded_total == Decimal("335.66")
    assert result.round_off == Decimal("0.34")
    assert result.final_total == Decimal("336.00")


def test_invoice_rejects_negative_taxable_value_from_excessive_discount(
    client, auth_headers, staff_user, branch
):
    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json=_invoice_payload(branch, discount="100.01"),
    )

    assert response.status_code == 422
    assert "discount" in str(response.json()["detail"]).lower()


def test_invoice_preview_persisted_draft_and_approval_totals_are_identical(
    client, auth_headers, staff_user, admin_user, branch
):
    payload = _invoice_payload(branch, quantity="9798.000")
    preview = client.post("/api/v1/invoices/preview", headers=auth_headers(staff_user), json=payload)
    created = client.post(
        "/api/v1/invoices",
        headers={**auth_headers(staff_user), "Idempotency-Key": "preview-save-001"},
        json=payload,
    )

    assert preview.status_code == 200
    assert created.status_code == 201
    preview_body = preview.json()
    created_body = created.json()
    for field in ("taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "cess_amount", "final_total"):
        assert created_body[field] == preview_body[field]

    invoice_id = created_body["id"]
    assert client.post(f"/api/v1/invoices/{invoice_id}/submit", headers=auth_headers(staff_user)).status_code == 200
    approved = client.post(f"/api/v1/invoices/{invoice_id}/approve", headers=auth_headers(admin_user))
    assert approved.status_code == 200
    approved_body = approved.json()
    for field in ("taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "cess_amount", "final_total"):
        assert approved_body[field] == preview_body[field]


def test_invoice_rejects_whitespace_required_fields_and_invalid_state_code(
    client, auth_headers, staff_user, branch
):
    payload = _invoice_payload(branch)
    payload["buyer"]["billing_address"]["address_line1"] = "   "
    whitespace_response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json=payload,
    )
    assert whitespace_response.status_code == 422

    invalid_state_payload = _invoice_payload(branch)
    invalid_state_payload["place_of_supply_state_code"] = "AA"
    invalid_state_response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json=invalid_state_payload,
    )
    assert invalid_state_response.status_code == 422


def test_invoice_rejects_non_finite_and_inappropriate_tax_values(
    client, auth_headers, staff_user, branch
):
    non_finite_payload = _invoice_payload(branch)
    non_finite_payload["lines"][0]["rate"] = "NaN"
    non_finite_response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json=non_finite_payload,
    )
    assert non_finite_response.status_code == 422

    excessive_tax_payload = _invoice_payload(branch)
    excessive_tax_payload["lines"][0]["gst_rate"] = "100.01"
    excessive_tax_response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json=excessive_tax_payload,
    )
    assert excessive_tax_response.status_code == 422


def test_explicitly_inactive_inline_parties_are_rejected(
    client, auth_headers, staff_user, branch
):
    invoice_payload = _invoice_payload(branch)
    invoice_payload["buyer"]["is_active"] = False
    invoice_response = client.post(
        "/api/v1/invoices", headers=auth_headers(staff_user), json=invoice_payload
    )
    assert invoice_response.status_code == 422
    assert "inactive" in str(invoice_response.json()["detail"]).lower()

    po_payload = _purchase_order_payload(branch)
    po_payload["supplier"]["is_active"] = False
    po_response = client.post(
        "/api/v1/purchase-orders", headers=auth_headers(staff_user), json=po_payload
    )
    assert po_response.status_code == 422
    assert "inactive" in str(po_response.json()["detail"]).lower()


def test_inline_customer_details_are_snapshotted_without_overwriting_matching_master(
    client, auth_headers, staff_user, branch, db_session
):
    old_customer = client.post(
        "/api/v1/customers",
        headers=auth_headers(staff_user),
        json={
            "branch_id": branch.id,
            **_customer("Old Buyer", "36ABCDE1234F1Z5", address_line1="Old Street"),
        },
    )
    assert old_customer.status_code == 201

    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json=_invoice_payload(
            branch,
            buyer=_customer("New Transaction Buyer", "36ABCDE1234F1Z5", address_line1="New Street"),
        ),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["buyer_name"] == "New Transaction Buyer"
    assert body["buyer_address_line1"] == "New Street"
    master = db_session.get(Customer, old_customer.json()["id"])
    assert master.name == "Old Buyer"
    assert master.billing_address_line1 == "Old Street"


def test_inline_supplier_details_are_snapshotted_without_overwriting_matching_master(
    client, auth_headers, staff_user, branch, db_session
):
    old_supplier = client.post(
        "/api/v1/suppliers",
        headers=auth_headers(staff_user),
        json={
            "branch_id": branch.id,
            "name": "Old Supplier",
            "gstin": "36FGHIJ1234K1Z5",
            "address": _address("Old Supplier Office", address_line1="Old Supplier Street"),
            "is_active": True,
        },
    )
    assert old_supplier.status_code == 201

    response = client.post(
        "/api/v1/purchase-orders",
        headers=auth_headers(staff_user),
        json=_purchase_order_payload(branch, supplier_name="New Transaction Supplier"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["supplier_name"] == "New Transaction Supplier"
    assert body["supplier_address_line1"] == "Billing Street 1"
    master = db_session.get(Supplier, old_supplier.json()["id"])
    assert master.name == "Old Supplier"
    assert master.address_line1 == "Old Supplier Street"


def test_explicit_null_lines_is_not_treated_as_an_omitted_patch(
    client, auth_headers, staff_user, branch
):
    created = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json=_invoice_payload(branch),
    )
    assert created.status_code == 201

    response = client.patch(
        f"/api/v1/invoices/{created.json()['id']}",
        headers=auth_headers(staff_user),
        json={"lines": None},
    )

    assert response.status_code == 422
    assert "lines" in str(response.json()["detail"]).lower()


def test_invoice_creation_idempotency_replays_and_conflicts_on_payload_change(
    client, auth_headers, staff_user, branch, db_session
):
    payload = _invoice_payload(branch)
    headers = {**auth_headers(staff_user), "Idempotency-Key": "invoice-create-001"}
    first = client.post("/api/v1/invoices", headers=headers, json=payload)
    replay = client.post("/api/v1/invoices", headers=headers, json=payload)

    changed_payload = {**payload, "po_number": "different-po"}
    conflict = client.post("/api/v1/invoices", headers=headers, json=changed_payload)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert conflict.status_code == 409
    assert db_session.scalar(select(func.count()).select_from(Invoice)) == 1


def test_purchase_order_creation_idempotency_replays_and_conflicts_on_payload_change(
    client, auth_headers, staff_user, branch, db_session
):
    payload = _purchase_order_payload(branch)
    headers = {**auth_headers(staff_user), "Idempotency-Key": "po-create-001"}
    first = client.post("/api/v1/purchase-orders", headers=headers, json=payload)
    replay = client.post("/api/v1/purchase-orders", headers=headers, json=payload)

    changed_payload = {**payload, "payment_terms": "30 days"}
    conflict = client.post("/api/v1/purchase-orders", headers=headers, json=changed_payload)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert conflict.status_code == 409
    assert db_session.scalar(select(func.count()).select_from(PurchaseOrder)) == 1


def test_idempotency_key_scope_is_enforced_by_database(db_session, branch):
    first = InvoiceCreationRequest(
        branch_id=branch.id,
        idempotency_key="database-scope-001",
        payload_hash="a" * 64,
    )
    second = InvoiceCreationRequest(
        branch_id=branch.id,
        idempotency_key="database-scope-001",
        payload_hash="b" * 64,
    )
    db_session.add(first)
    db_session.commit()
    db_session.add(second)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    po_first = PurchaseOrderCreationRequest(
        branch_id=branch.id,
        idempotency_key="database-po-scope-001",
        payload_hash="a" * 64,
    )
    po_second = PurchaseOrderCreationRequest(
        branch_id=branch.id,
        idempotency_key="database-po-scope-001",
        payload_hash="b" * 64,
    )
    db_session.add(po_first)
    db_session.commit()
    db_session.add(po_second)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_new_transactions_reject_inactive_saved_masters(
    client, auth_headers, staff_user, branch
):
    customer_payload = _customer("Inactive Buyer", "36ABCDE1234F1Z5")
    customer_payload["branch_id"] = branch.id
    customer = client.post("/api/v1/customers", headers=auth_headers(staff_user), json=customer_payload)
    product = client.post(
        "/api/v1/products",
        headers=auth_headers(staff_user),
        json={
            "branch_id": branch.id,
            "name": "Inactive Material",
            "description": "Inactive material",
            "hsn_sac": "29181590",
            "unit": "KG",
            "base_rate": "100.00",
            "gst_rate": "18.00",
            "cess_rate": "0.00",
            "is_active": True,
        },
    )
    assert customer.status_code == 201
    assert product.status_code == 201

    assert client.patch(
        f"/api/v1/customers/{customer.json()['id']}",
        headers=auth_headers(staff_user),
        json={"is_active": False},
    ).status_code == 200
    assert client.patch(
        f"/api/v1/products/{product.json()['id']}",
        headers=auth_headers(staff_user),
        json={"is_active": False},
    ).status_code == 200

    response = client.post(
        "/api/v1/invoices",
        headers=auth_headers(staff_user),
        json={
            "branch_id": branch.id,
            "buyer_customer_id": customer.json()["id"],
            "invoice_date": "2026-09-16",
            "invoice_number_suffix": "INACTIVE-001",
            "place_of_supply_state_code": "36",
            "lines": [{"product_id": product.json()["id"], "quantity": "1.000"}],
        },
    )

    assert response.status_code == 422
    assert "inactive" in str(response.json()["detail"]).lower()
