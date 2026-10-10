from app.models.invoice import InvoiceAuditLog
from app.models.purchase_order import PurchaseOrderAuditLog, PurchaseOrderRevision
from tests.test_financial_correctness import _purchase_order_payload
from tests.test_invoices import _create_customer, _create_invoice, _create_product, _invoice_payload


def _invoice_for_workflow(client, auth_headers, staff_user, branch):
    customer = _create_customer(client, auth_headers, staff_user, branch)
    product = _create_product(client, auth_headers, staff_user, branch)
    return _create_invoice(client, auth_headers, staff_user, branch, customer["id"], product["id"]), customer, product


def test_invoice_return_for_correction_preserves_reviewed_revision_and_blocks_self_approval(
    client, auth_headers, staff_user, manager_user, branch, db_session
):
    invoice, _, _ = _invoice_for_workflow(client, auth_headers, staff_user, branch)
    submitted = client.post(f"/api/v1/invoices/{invoice['id']}/submit", headers=auth_headers(staff_user))
    assert submitted.status_code == 200
    assert submitted.json()["submitted_revision"] == 1

    self_approval = client.post(f"/api/v1/invoices/{invoice['id']}/approve", headers=auth_headers(staff_user))
    assert self_approval.status_code == 403

    returned = client.post(
        f"/api/v1/invoices/{invoice['id']}/return-for-correction",
        headers=auth_headers(manager_user),
        json={"reason": "Please confirm the delivery date."},
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "draft"
    assert returned.json()["version"] == 2
    assert returned.json()["returned_reason"] == "Please confirm the delivery date."
    assert db_session.query(InvoiceAuditLog).filter_by(invoice_id=invoice["id"]).count() == 2


def test_admin_can_self_approve_invoice_and_purchase_order(
    client, auth_headers, admin_user, branch
):
    customer = _create_customer(client, auth_headers, admin_user, branch)
    product = _create_product(client, auth_headers, admin_user, branch)
    invoice = _create_invoice(client, auth_headers, admin_user, branch, customer["id"], product["id"])

    submitted_invoice = client.post(
        f"/api/v1/invoices/{invoice['id']}/submit", headers=auth_headers(admin_user)
    )
    approved_invoice = client.post(
        f"/api/v1/invoices/{invoice['id']}/approve", headers=auth_headers(admin_user)
    )
    assert submitted_invoice.status_code == 200
    assert approved_invoice.status_code == 200
    assert approved_invoice.json()["status"] == "approved"

    created_order = client.post(
        "/api/v1/purchase-orders",
        headers=auth_headers(admin_user),
        json=_purchase_order_payload(branch),
    )
    assert created_order.status_code == 201
    order_id = created_order.json()["id"]
    submitted_order = client.post(
        f"/api/v1/purchase-orders/{order_id}/submit", headers=auth_headers(admin_user)
    )
    approved_order = client.post(
        f"/api/v1/purchase-orders/{order_id}/approve", headers=auth_headers(admin_user)
    )
    assert submitted_order.status_code == 200
    assert approved_order.status_code == 200
    assert approved_order.json()["status"] == "approved"


def test_invoice_patch_reports_version_conflict_instead_of_overwriting_newer_draft(
    client, auth_headers, staff_user, branch
):
    invoice, _, _ = _invoice_for_workflow(client, auth_headers, staff_user, branch)
    changed = client.patch(
        f"/api/v1/invoices/{invoice['id']}",
        headers=auth_headers(staff_user),
        json={"expected_version": 1, "payment_terms": "45 days"},
    )
    assert changed.status_code == 200
    assert changed.json()["version"] == 2

    stale = client.patch(
        f"/api/v1/invoices/{invoice['id']}",
        headers=auth_headers(staff_user),
        json={"expected_version": 1, "payment_terms": "60 days"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"
    assert stale.json()["detail"]["current_version"] == 2


def test_purchase_order_lifecycle_records_amendment_history_and_rejects_stale_edits(
    client, auth_headers, staff_user, manager_user, branch, db_session
):
    created = client.post(
        "/api/v1/purchase-orders",
        headers=auth_headers(staff_user),
        json=_purchase_order_payload(branch),
    )
    assert created.status_code == 201
    purchase_order = created.json()
    submitted = client.post(f"/api/v1/purchase-orders/{purchase_order['id']}/submit", headers=auth_headers(staff_user))
    assert submitted.status_code == 200
    approved = client.post(f"/api/v1/purchase-orders/{purchase_order['id']}/approve", headers=auth_headers(manager_user))
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    amended = client.post(
        f"/api/v1/purchase-orders/{purchase_order['id']}/amend",
        headers=auth_headers(staff_user),
        json={"expected_version": approved.json()["version"], "reason": "Supplier changed expected delivery date."},
    )
    assert amended.status_code == 200
    assert amended.json()["status"] == "amendment_pending"
    assert db_session.query(PurchaseOrderRevision).filter_by(purchase_order_id=purchase_order["id"]).count() >= 2
    assert db_session.query(PurchaseOrderAuditLog).filter_by(purchase_order_id=purchase_order["id"]).count() >= 3

    stale = client.patch(
        f"/api/v1/purchase-orders/{purchase_order['id']}",
        headers=auth_headers(staff_user),
        json={"expected_version": 1, "payment_terms": "60 days"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"


def test_registers_and_dashboard_return_real_authorized_data(
    client, auth_headers, staff_user, manager_user, branch
):
    invoice, customer, product = _invoice_for_workflow(client, auth_headers, staff_user, branch)
    client.post(f"/api/v1/invoices/{invoice['id']}/submit", headers=auth_headers(staff_user))
    client.post(
        "/api/v1/purchase-orders",
        headers=auth_headers(staff_user),
        json=_purchase_order_payload(branch),
    )

    register = client.get("/api/v1/invoices/register?q=Apex&page=1&page_size=10", headers=auth_headers(manager_user))
    assert register.status_code == 200
    assert register.json()["total"] == 1
    assert register.json()["items"][0]["id"] == invoice["id"]
    queue = client.get("/api/v1/invoices/approval-queue", headers=auth_headers(manager_user))
    assert queue.status_code == 200
    assert queue.json()[0]["id"] == invoice["id"]
    dashboard = client.get("/api/v1/dashboard", headers=auth_headers(manager_user))
    assert dashboard.status_code == 200
    assert dashboard.json()["pending_invoice_approvals"] == 1
    assert "outstanding_payments" not in dashboard.json()
