"""Standalone reagent-style Credit Notes never create receivables entries."""
from datetime import UTC, datetime
from copy import deepcopy
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.v1.invoices import update_invoice
from app.models.enums import InvoiceStatus
from app.models.invoice import Invoice, InvoiceAuditLog
from app.schemas.invoice import InvoiceUpdate
from app.services.invoice_pdf import build_invoice_context, build_invoice_html
from tests.test_invoices import _create_customer, _create_invoice, _create_product, _invoice_payload
from tests.test_phase5b_integration_readiness import _job_payload


def _payload(client, auth_headers, user, branch, suffix="001", state="36"):
    customer = _create_customer(client, auth_headers, user, branch)
    product = _create_product(client, auth_headers, user, branch)
    manufacturer_code = f"CNR{branch.id}"
    manufacturer_response = client.post(
        "/api/v1/manufacturers",
        headers=auth_headers(user),
        json={"branch_id": branch.id, "code": manufacturer_code, "name": "Merck"},
    )
    if manufacturer_response.status_code == 201:
        manufacturer = manufacturer_response.json()
    else:
        assert manufacturer_response.status_code == 409, manufacturer_response.text
        manufacturers = client.get(
            "/api/v1/manufacturers?active_only=true", headers=auth_headers(user)
        )
        assert manufacturers.status_code == 200, manufacturers.text
        manufacturer = next(
            item for item in manufacturers.json()
            if item["branch_id"] == branch.id and item["code"] == manufacturer_code
        )
    payload = _invoice_payload(branch, customer["id"], product["id"], state, suffix)
    payload["document_type"] = "credit_note"
    payload["lines"][0].update({
        "manufacturer_id": manufacturer["id"],
        "manufacturer_product_code": "CN-ART-001",
        "part_no": "CN-ART-001",
        "pack_size": "500 g",
        "unit": "kg",
        "discount_percent": "0.00",
    })
    return payload


def _create(client, headers, payload):
    response = client.post("/api/v1/invoices", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _approve(client, auth_headers, creator, reviewer, document):
    path = f"/api/v1/invoices/{document['id']}"
    submitted = client.post(path + "/submit", headers=auth_headers(creator), json={"expected_version": document["version"]})
    assert submitted.status_code == 200, submitted.text
    approved = client.post(path + "/approve", headers=auth_headers(reviewer), json={"expected_version": document["version"]})
    assert approved.status_code == 200, approved.text
    return approved.json()


@pytest.mark.parametrize("state,cgst,igst", [("36", "26454.60", "0.00"), ("29", "0.00", "52909.20")])
def test_credit_note_preview_draft_and_approval_use_reagent_fields_and_decimal_totals(
    client, auth_headers, staff_user, manager_user, branch, state, cgst, igst,
):
    payload = _payload(client, auth_headers, staff_user, branch, state=state)
    preview = client.post("/api/v1/invoices/preview", headers=auth_headers(staff_user), json=payload)
    assert preview.status_code == 200, preview.text
    draft = _create(client, auth_headers(staff_user), payload)
    approved = _approve(client, auth_headers, staff_user, manager_user, draft)
    for document in (preview.json(), draft, approved):
        assert document["taxable_value"] == "293940.00"
        assert document["cgst_amount"] == cgst
        assert document["sgst_amount"] == cgst
        assert document["igst_amount"] == igst
        assert document["final_total"] == "346849.00"
        assert document["lines"][0]["manufacturer_name"] == "Merck"
        assert document["lines"][0]["manufacturer_product_code"] == "CN-ART-001"
        assert document["lines"][0]["part_no"] == "CN-ART-001"
        assert document["lines"][0]["pack_size"] == "500 g"
        assert document["lines"][0]["unit"] == "kg"
    assert approved["invoice_number"] == "PBPL/CN/2026-27/001"
    assert approved["document_type"] == "credit_note"
    denied = client.patch(f"/api/v1/invoices/{draft['id']}", headers=auth_headers(staff_user), json={"payment_terms": "overwrite", "expected_version": draft["version"]})
    assert denied.status_code == 409


def test_credit_note_requires_reagent_manufacturer_and_supported_unit(
    client, auth_headers, staff_user, branch,
):
    valid_payload = _payload(client, auth_headers, staff_user, branch)
    payload = deepcopy(valid_payload)
    payload["lines"][0].pop("manufacturer_id")
    missing_manufacturer = client.post(
        "/api/v1/invoices/preview", headers=auth_headers(staff_user), json=payload
    )
    assert missing_manufacturer.status_code == 422
    assert "manufacturer" in missing_manufacturer.text.lower()

    payload = deepcopy(valid_payload)
    payload["lines"][0]["unit"] = "BOX"
    invalid_unit = client.post(
        "/api/v1/invoices/preview", headers=auth_headers(staff_user), json=payload
    )
    assert invalid_unit.status_code == 422
    assert "unit must be one of" in invalid_unit.text


def test_credit_note_numbering_is_separate_unique_idempotent_and_follows_financial_year(
    client, auth_headers, staff_user, branch,
):
    payload = _payload(client, auth_headers, staff_user, branch)
    sales = _create_invoice(client, auth_headers, staff_user, branch, payload["buyer_customer_id"], payload["lines"][0]["product_id"], invoice_number_suffix="001")
    headers = {**auth_headers(staff_user), "Idempotency-Key": "credit-note-save-001"}
    note = _create(client, headers, payload)
    assert note["invoice_number"] != sales["invoice_number"]
    replay = client.post("/api/v1/invoices", headers=headers, json=payload)
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == note["id"]
    changed = client.post("/api/v1/invoices", headers=headers, json={**payload, "payment_terms": "changed"})
    assert changed.status_code == 409
    duplicate = client.post("/api/v1/invoices", headers=auth_headers(staff_user), json=payload)
    assert duplicate.status_code == 409
    path = f"/api/v1/invoices/{note['id']}"
    updated = client.patch(path, headers=auth_headers(staff_user), json={"invoice_date": "2027-04-01", "expected_version": note["version"]})
    assert updated.status_code == 200, updated.text
    assert updated.json()["invoice_number"] == "PBPL/CN/2027-28/001"
    stale = client.patch(path, headers=auth_headers(staff_user), json={"payment_terms": "stale", "expected_version": note["version"]})
    assert stale.status_code == 409


def test_credit_note_register_counts_and_details_are_type_and_profile_scoped(
    client, auth_headers, staff_user, admin_user, branch, other_branch,
):
    payload = _payload(client, auth_headers, staff_user, branch)
    note = _create(client, auth_headers(staff_user), payload)
    _create_invoice(client, auth_headers, staff_user, branch, payload["buyer_customer_id"], payload["lines"][0]["product_id"])
    hidden = _create(client, auth_headers(admin_user), _payload(client, auth_headers, admin_user, other_branch, suffix="002"))
    registered = client.get("/api/v1/invoices/register?document_type=credit_note&date_from=2026-08-25&date_to=2026-08-25", headers=auth_headers(staff_user))
    assert registered.status_code == 200, registered.text
    assert registered.json()["total"] == 1
    assert registered.json()["items"][0]["id"] == note["id"]
    assert client.get("/api/v1/invoices?document_type=credit_note", headers=auth_headers(staff_user)).json()[0]["id"] == note["id"]
    assert client.get(f"/api/v1/invoices/{hidden['id']}", headers=auth_headers(staff_user)).status_code == 403
    dashboard = client.get("/api/v1/dashboard", headers=auth_headers(staff_user)).json()
    assert dashboard["credit_note_count"] == 1
    assert dashboard["sales_invoice_count"] == 1
    assert dashboard["invoice_count"] == 1
    assert client.get("/api/v1/invoices/register", headers=auth_headers(staff_user)).json()["total"] == 1


def test_credit_note_staff_permissions_audit_and_confirmed_correction(
    client, auth_headers, staff_user, manager_user, branch, db_session,
):
    payload = _payload(client, auth_headers, staff_user, branch)
    note = _create(client, auth_headers(staff_user), payload)
    path = f"/api/v1/invoices/{note['id']}"
    assert client.post(path + "/approve", headers=auth_headers(staff_user)).status_code == 403
    approved = _approve(client, auth_headers, staff_user, manager_user, note)
    opened = client.get(path + "/correction?edit=1", headers=auth_headers(staff_user))
    assert opened.status_code == 200, opened.text
    saved = client.patch(path + "/correction", headers=auth_headers(staff_user), json={"expected_version": opened.json()["version"], "correction_reason": "Correct entered payment terms", "payment_terms": "45 days", "invoice_number_suffix": "001"})
    assert saved.status_code == 200, saved.text
    assert client.get(path, headers=auth_headers(staff_user)).json()["payment_terms"] == approved["payment_terms"]
    revision = saved.json()["version"]
    assert client.post(path + "/correction/submit", headers=auth_headers(staff_user), json={"expected_version": revision}).status_code == 200
    corrected = client.post(path + "/correction/approve", headers=auth_headers(manager_user), json={"expected_version": revision})
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["id"] == note["id"]
    assert corrected.json()["invoice_number"] == "PBPL/CN/2026-27/001"
    assert corrected.json()["payment_terms"] == "45 days"
    assert corrected.json()["document_type"] == "credit_note"
    transitions = db_session.scalars(select(InvoiceAuditLog).where(InvoiceAuditLog.invoice_id == note["id"])).all()
    assert {row.to_status for row in transitions} >= {InvoiceStatus.PENDING_APPROVAL, InvoiceStatus.APPROVED}


def _stored_note(client, auth_headers, staff_user, manager_user, branch, db_session):
    payload = _payload(client, auth_headers, staff_user, branch)
    note = _create(client, auth_headers(staff_user), payload)
    approved = _approve(client, auth_headers, staff_user, manager_user, note)
    invoice = db_session.get(Invoice, approved["id"])
    return invoice


def test_document_only_credit_note_is_excluded_from_statements_ageing_and_exports(
    client, auth_headers, staff_user, manager_user, branch, db_session,
):
    note = _stored_note(client, auth_headers, staff_user, manager_user, branch, db_session)
    root = f"/api/v1/payments/customers/{note.buyer_customer_id}"
    assert client.get(root + "/statement", headers=auth_headers(staff_user)).json()["total"] == 0
    assert Decimal(client.get(root + "/ageing", headers=auth_headers(staff_user)).json()["total_outstanding"]) == 0
    export = client.get(root + "/statement.csv", headers=auth_headers(manager_user))
    assert export.status_code == 200
    assert note.invoice_number not in export.text


def test_document_only_credit_note_cannot_receive_payments_or_external_jobs(
    client, auth_headers, staff_user, manager_user, branch, db_session,
):
    note = _stored_note(client, auth_headers, staff_user, manager_user, branch, db_session)
    receipt = client.post("/api/v1/payments/receipts", headers={**auth_headers(staff_user), "Idempotency-Key": "cn-receipt"}, json={"customer_id": note.buyer_customer_id, "receipt_date": "2026-10-23", "amount": "100.00"})
    assert receipt.status_code == 201, receipt.text
    allocated = client.post("/api/v1/payments/allocations", headers={**auth_headers(staff_user), "Idempotency-Key": "cn-allocation"}, json={"receipt_id": receipt.json()["id"], "invoice_id": note.id, "amount": "10.00"})
    assert allocated.status_code == 422, allocated.text
    assert "document-only" in allocated.json()["detail"]
    external = client.post("/api/v1/integrations/jobs", headers={**auth_headers(manager_user), "Idempotency-Key": "cn-external"}, json=_job_payload(note.id, branch.id))
    assert external.status_code == 422, external.text
    assert "document-only" in external.json()["detail"]


def test_credit_note_pdf_uses_reagent_fields_and_keeps_credit_note_identity(
    client, auth_headers, staff_user, manager_user, branch, db_session,
):
    note = _stored_note(client, auth_headers, staff_user, manager_user, branch, db_session)
    context = build_invoice_context(note, branch=branch, generated_at=datetime(2026, 10, 23, tzinfo=UTC))
    html = build_invoice_html(context)
    assert context.document_title == "Credit Note"
    assert context.document_number_label == "Credit Note No"
    assert context.document_type == "reagent"
    assert context.template_version == "a4-credit-note-v2"
    assert len(context.copy_labels) == 4
    assert "Credit Note No" in html
    for text in (
        "Buyer Details", "Consignee / Shipping Details", "Sodium Citrate",
        "MFG: Merck, Artical No.: CN-ART-001", "Pack/Size", "500 g",
        "Disc %", "Terms and Conditions:", "Computer Generated Credit Note",
        "Vehicle No.",
    ):
        assert text in html
    assert "Other Charge" not in html
    assert "Cess</th>" not in html
    assert "Tax Invoice" not in html
    assert context.buyer.contact == "9876543210 | billing@apex.example"
    assert context.buyer.email is None


def test_credit_note_inherited_delete_action_requires_admin_and_releases_only_its_number(
    client, auth_headers, staff_user, admin_user, branch,
):
    payload = _payload(client, auth_headers, staff_user, branch)
    note = _create(client, {**auth_headers(staff_user), "Idempotency-Key": "note-to-delete"}, payload)
    path = f"/api/v1/invoices/{note['id']}"
    body = {"document_type": "credit_note", "confirmation_number": note["invoice_number"], "expected_version": note["version"]}
    assert client.request("DELETE", path, headers=auth_headers(staff_user), json=body).status_code == 403
    deleted = client.request("DELETE", path, headers=auth_headers(admin_user), json=body)
    assert deleted.status_code == 204, deleted.text
    assert client.get(path, headers=auth_headers(admin_user)).status_code == 404
    old_retry = client.post("/api/v1/invoices", headers={**auth_headers(staff_user), "Idempotency-Key": "note-to-delete"}, json=payload)
    assert old_retry.status_code == 410
    fresh = _create(client, auth_headers(staff_user), payload)
    assert fresh["invoice_number"] == note["invoice_number"]


def test_credit_note_concurrent_number_conflict_reports_its_own_number(
    client, auth_headers, staff_user, branch, db_session, monkeypatch,
):
    note = _create(client, auth_headers(staff_user), _payload(client, auth_headers, staff_user, branch))

    def concurrent_conflict():
        raise IntegrityError("UPDATE invoices", {}, Exception("UNIQUE constraint failed: invoices.invoice_number"))

    # Simulate the commit-time race, not a sequential preflight collision.
    monkeypatch.setattr(db_session, "commit", concurrent_conflict)
    with pytest.raises(HTTPException) as caught:
        update_invoice(note["id"], InvoiceUpdate(invoice_number_suffix="002", expected_version=note["version"]), db_session, staff_user)
    assert caught.value.status_code == 409
    assert "PBPL/CN/2026-27/002" in caught.value.detail
