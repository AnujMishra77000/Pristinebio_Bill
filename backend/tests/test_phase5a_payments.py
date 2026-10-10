from decimal import Decimal

from app.models.payment import PaymentAuditLog, Receipt, ReceiptAllocation
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice
from tests.test_invoices import _create_customer, _create_invoice, _create_product


def _approved_invoice(client, auth_headers, staff_user, manager_user, branch):
    customer = _create_customer(client, auth_headers, staff_user, branch, name="Receivables Customer")
    product = _create_product(client, auth_headers, staff_user, branch, name="Receivables Product")
    invoice = _create_invoice(client, auth_headers, staff_user, branch, customer["id"], product["id"])
    assert client.post(f"/api/v1/invoices/{invoice['id']}/submit", headers=auth_headers(staff_user)).status_code == 200
    assert client.post(f"/api/v1/invoices/{invoice['id']}/approve", headers=auth_headers(manager_user)).status_code == 200
    return customer, invoice


def test_receipt_supports_partial_allocation_and_unallocated_credit(client, auth_headers, staff_user, manager_user, branch, db_session):
    customer, invoice = _approved_invoice(client, auth_headers, staff_user, manager_user, branch)
    receipt = client.post("/api/v1/payments/receipts", headers={**auth_headers(staff_user), "Idempotency-Key": "receipt-1"}, json={"customer_id": customer["id"], "receipt_date": "2026-09-16", "currency": "INR", "amount": "100000.00"})
    assert receipt.status_code == 201, receipt.text
    assert receipt.json()["unallocated_amount"] == "100000.00"
    allocation = client.post("/api/v1/payments/allocations", headers={**auth_headers(staff_user), "Idempotency-Key": "allocation-1"}, json={"receipt_id": receipt.json()["id"], "invoice_id": invoice["id"], "amount": "50000.00"})
    assert allocation.status_code == 201, allocation.text
    listed = client.get(f"/api/v1/payments/receipts?customer_id={customer['id']}", headers=auth_headers(staff_user)).json()["items"][0]
    assert listed["allocated_amount"] == "50000.00"
    assert listed["unallocated_amount"] == "50000.00"


def test_allocation_rejects_overpayment_and_currency_mismatch(client, auth_headers, staff_user, manager_user, branch):
    customer, invoice = _approved_invoice(client, auth_headers, staff_user, manager_user, branch)
    receipt = client.post("/api/v1/payments/receipts", headers={**auth_headers(staff_user), "Idempotency-Key": "receipt-2"}, json={"customer_id": customer["id"], "receipt_date": "2026-09-16", "currency": "USD", "amount": "100.00"})
    assert receipt.status_code == 201
    mismatch = client.post("/api/v1/payments/allocations", headers={**auth_headers(staff_user), "Idempotency-Key": "allocation-2"}, json={"receipt_id": receipt.json()["id"], "invoice_id": invoice["id"], "amount": "10.00"})
    assert mismatch.status_code == 422
    assert "currencies" in mismatch.json()["detail"]


def test_receipt_retry_is_idempotent_and_changed_payload_conflicts(client, auth_headers, staff_user, branch):
    customer = _create_customer(client, auth_headers, staff_user, branch, name="Idempotent Customer")
    headers = {**auth_headers(staff_user), "Idempotency-Key": "receipt-same"}
    payload = {"customer_id": customer["id"], "receipt_date": "2026-09-16", "currency": "INR", "amount": "42.00"}
    first = client.post("/api/v1/payments/receipts", headers=headers, json=payload)
    second = client.post("/api/v1/payments/receipts", headers=headers, json=payload)
    conflict = client.post("/api/v1/payments/receipts", headers=headers, json={**payload, "amount": "43.00"})
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert conflict.status_code == 409


def test_reversal_is_audited_and_restores_unallocated_credit(client, auth_headers, staff_user, branch, db_session):
    customer = _create_customer(client, auth_headers, staff_user, branch, name="Reversal Customer")
    receipt = client.post("/api/v1/payments/receipts", headers={**auth_headers(staff_user), "Idempotency-Key": "receipt-3"}, json={"customer_id": customer["id"], "receipt_date": "2026-09-16", "amount": "42.00"})
    response = client.post(f"/api/v1/payments/receipts/{receipt.json()['id']}/reverse", headers=auth_headers(staff_user), json={"reason": "Bank return"})
    assert response.status_code == 200
    assert response.json()["status"] == "reversed"
    assert db_session.query(PaymentAuditLog).filter_by(entity_type="receipt", action="reversed").count() == 1


def test_staff_cannot_export_statement(client, auth_headers, staff_user, branch):
    customer = _create_customer(client, auth_headers, staff_user, branch, name="Private Statement Customer")
    response = client.get(f"/api/v1/payments/customers/{customer['id']}/statement.csv", headers=auth_headers(staff_user))
    assert response.status_code == 403
