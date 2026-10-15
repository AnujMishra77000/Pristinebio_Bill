"""Corrections must never replace a confirmed document before approval."""
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
import hashlib

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.enums import InvoiceStatus
from app.models.bill_correction import BillCorrection
from app.models.invoice import Invoice, InvoiceRevision
from app.models.purchase_order import PurchaseOrder, PurchaseOrderRevision
from app.models.integration import OutboundIntegrationJob
from app.models.payment import Receipt, ReceiptAllocation
from app.models.authentication import SecurityAudit
from app.models.master_records import Supplier
from app.models.invoice import InvoiceAuditLog
from app.services.invoice_pdf import PdfGenerationResult, build_invoice_html
from tests.test_inline_submission import DOCUMENTS, _document


def confirmed(kind, client, auth_headers, creator, manager, branch, db, monkeypatch, tmp_path):
    url, original, payload = _document(kind, client, auth_headers, creator, branch)
    submitted = client.post(url + "/submit", headers=auth_headers(creator), json={"expected_version": original["version"]})
    assert submitted.status_code == 200, submitted.text
    response = client.post(url + "/approve", headers=auth_headers(manager), json={"expected_version": original["version"]})
    assert response.status_code == 200, response.text
    model = PurchaseOrder if "purchase-orders" in url else Invoice
    bill = db.get(model, original["id"])
    monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(tmp_path))
    old_pdf = b"%PDF-original-confirmed-document"
    key = f"original-{kind}-{bill.id}.pdf"
    (tmp_path / key).write_bytes(old_pdf)
    bill.pdf_storage_key = key
    bill.pdf_sha256 = hashlib.sha256(old_pdf).hexdigest()
    bill.pdf_template_version = "historical-template"
    bill.pdf_generated_by_id = manager.id
    bill.pdf_generated_at = datetime.now(UTC)
    if model is Invoice:
        bill.status = InvoiceStatus.PDF_GENERATED
    db.commit()
    return url, client.get(url, headers=auth_headers(creator)).json(), payload, model, key, old_pdf


def correction_update(kind, payload, version, **extra):
    edited = deepcopy(payload)
    edited["lines"][0].update(quantity="2.000", rate="100.00", gst_rate="18.00", discount_percent="0.00", discount_amount="0.00", other_charge="0.00", product_name="Corrected transaction name")
    edited["payment_terms"] = "Corrected payment terms"
    if kind in {"domestic_oils", "reagent_po"}:
        fields = {"reagent_details" if kind == "reagent_po" else "domestic_details": edited}
    else:
        edited.pop("document_type", None)
        fields = edited
    return {**fields, "expected_version": version, "correction_reason": "Correct entered quantity", **extra}


@pytest.mark.parametrize("kind", DOCUMENTS)
def test_confirmed_correction_keeps_original_until_independent_approval_then_replaces_same_id_and_number(
    kind, client, auth_headers, staff_user, manager_user, branch, db_session, monkeypatch, tmp_path,
):
    url, original, payload, model, key, old_pdf = confirmed(kind, client, auth_headers, staff_user, manager_user, branch, db_session, monkeypatch, tmp_path)
    path = url + "/correction"
    opened = client.get(path + "?edit=1", headers=auth_headers(staff_user))
    assert opened.status_code == 200, opened.text
    view = opened.json()
    assert view["status"] == "draft"
    assert view["id"] == original["id"]
    assert view["pdf_storage_key"] is None
    assert view["correction"]["base_version"] == original["version"]
    assert view["created_by_id"] == staff_user.id
    assert client.get(url + "/pdf", headers=auth_headers(staff_user)).content == old_pdf
    update = correction_update(kind, payload, view["version"])
    saved = client.patch(path, headers=auth_headers(staff_user), json=update)
    assert saved.status_code == 200, saved.text
    draft = saved.json()
    assert draft["lines"][0]["quantity"] == "2.000"
    assert draft["lines"][0]["product_name"] == "Corrected transaction name"
    assert Decimal(draft["final_total"]) == Decimal("236.00")
    assert client.get(url, headers=auth_headers(staff_user)).json() == original
    assert db_session.scalar(select(func.count()).select_from(model)) == 1
    stale = client.patch(path, headers=auth_headers(staff_user), json=update)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"
    submitted = client.post(path + "/submit", headers=auth_headers(staff_user), json={"expected_version": draft["version"]})
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "pending_approval"
    assert submitted.json()["submitted_by_id"] == staff_user.id
    assert submitted.json()["submitted_at"] != original["submitted_at"]
    denied = client.post(path + "/approve", headers=auth_headers(staff_user), json={"expected_version": draft["version"]})
    assert denied.status_code == 403
    queue = client.get("/api/v1/bill-corrections/pending", headers=auth_headers(manager_user))
    assert queue.status_code == 200, queue.text
    assert queue.json()["items"][0]["document_id"] == original["id"]
    assert queue.json()["items"][0]["final_total"] == "236.00"
    approved = client.post(path + "/approve", headers=auth_headers(manager_user), json={"expected_version": draft["version"]})
    assert approved.status_code == 200, approved.text
    changed = approved.json()
    number = "purchase_order_number" if model is PurchaseOrder else "invoice_number"
    assert changed["id"] == original["id"]
    assert changed[number] == original[number]
    assert Decimal(changed["final_total"]) == Decimal("236.00")
    assert changed["pdf_storage_key"] is None
    assert datetime.fromisoformat(changed["submitted_at"]).replace(tzinfo=None) == datetime.fromisoformat(submitted.json()["submitted_at"]).replace(tzinfo=None)
    assert changed.get("correction") is None
    assert client.get(url + "/pdf", headers=auth_headers(manager_user)).status_code == 404
    assert (tmp_path / key).read_bytes() == old_pdf
    revisions = PurchaseOrderRevision if model is PurchaseOrder else InvoiceRevision
    history = db_session.scalars(select(revisions).where(revisions.event == "correction_confirmed")).all()
    assert len(history) == 1
    assert history[0].snapshot["document"]["pdf_storage_key"] == key
    assert history[0].snapshot["document"]["final_total"] == original["final_total"]
    assert history[0].snapshot["after"]["document"]["final_total"] == "236.00"
    assert history[0].snapshot["after"]["lines"][0]["id"] == changed["lines"][0]["id"]
    # Lost approval response: the same exact revision replays without republishing.
    repeated = client.post(path + "/approve", headers=auth_headers(manager_user), json={"expected_version": draft["version"]})
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["version"] == changed["version"]
    assert client.get(path, headers=auth_headers(staff_user)).json()["status"] == "approved"
    reopened = client.get(path + "?edit=1", headers=auth_headers(staff_user))
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "draft"
    assert reopened.json()["correction"]["base_version"] == changed["version"]


@pytest.mark.parametrize("kind", DOCUMENTS)
def test_corrections_require_a_reason_versions_and_authorized_profile(
    kind, client, auth_headers, staff_user, admin_user, manager_user, branch, other_branch, db_session, monkeypatch, tmp_path,
):
    url, original, payload, _, _, _ = confirmed(kind, client, auth_headers, staff_user, manager_user, branch, db_session, monkeypatch, tmp_path)
    for reason in (None, "", "   "):
        update = correction_update(kind, payload, original["version"], correction_reason=reason)
        response = client.patch(url + "/correction", headers=auth_headers(staff_user), json=update)
        assert response.status_code == 422, response.text
    update = correction_update(kind, payload, original["version"])
    update.pop("expected_version")
    assert client.patch(url + "/correction", headers=auth_headers(staff_user), json=update).status_code == 422
    other_url, other, _, _, _, _ = confirmed(kind, client, auth_headers, admin_user, admin_user, other_branch, db_session, monkeypatch, tmp_path)
    assert client.get(other_url + "/correction?edit=1", headers=auth_headers(staff_user)).status_code == 403
    assert client.patch(other_url + "/correction", headers=auth_headers(staff_user), json=correction_update(kind, payload, other["version"])).status_code == 403
    assert client.get("/api/v1/bill-corrections/pending", headers=auth_headers(staff_user)).status_code == 403
    assert client.get(url, headers=auth_headers(staff_user)).json() == original


@pytest.mark.parametrize("kind", DOCUMENTS)
def test_correction_preview_uses_saved_changed_snapshot_and_final_pdf_never_reuses_old_bytes(
    kind, client, auth_headers, admin_user, branch, db_session, monkeypatch, tmp_path,
):
    url, original, payload, _, key, old_pdf = confirmed(kind, client, auth_headers, admin_user, admin_user, branch, db_session, monkeypatch, tmp_path)
    saved = client.patch(url + "/correction", headers=auth_headers(admin_user), json=correction_update(kind, payload, original["version"]))
    assert saved.status_code == 200, saved.text
    draft = saved.json()
    new_pdf = b"%PDF-corrected-confirmed-document"

    def render(context):
        assert "Corrected transaction name" in build_invoice_html(context)
        assert context.final_total == Decimal("236.00")
        return PdfGenerationResult(new_pdf, hashlib.sha256(new_pdf).hexdigest())

    module = "app.api.v1.purchase_orders.render_purchase_order_pdf" if "purchase-orders" in url else "app.api.v1.invoices.render_invoice_pdf"
    monkeypatch.setattr(module, render)
    preview = client.post(url + "/correction/preview-pdf", headers=auth_headers(admin_user), json={"expected_version": draft["version"]})
    assert preview.status_code == 200, preview.text
    assert preview.content == new_pdf
    assert client.get(url + "/pdf", headers=auth_headers(admin_user)).content == old_pdf
    assert client.post(url + "/correction/submit", headers=auth_headers(admin_user), json={"expected_version": draft["version"]}).status_code == 200
    response = client.post(url + "/correction/approve", headers=auth_headers(admin_user), json={"expected_version": draft["version"]})
    assert response.status_code == 200, response.text
    generated = client.post(url + "/generate-pdf", headers=auth_headers(admin_user))
    assert generated.status_code == 200, generated.text
    assert generated.json()["pdf_storage_key"] != key
    assert client.get(url + "/pdf", headers=auth_headers(admin_user)).content == new_pdf
    assert (tmp_path / key).read_bytes() == old_pdf


@pytest.mark.parametrize("dependency", ("payment", "integration", "irn"))
def test_financial_links_block_corrections_even_when_added_after_edit_started(
    dependency, client, auth_headers, admin_user, branch, db_session, monkeypatch, tmp_path,
):
    url, original, payload, _, _, _ = confirmed("sales", client, auth_headers, admin_user, admin_user, branch, db_session, monkeypatch, tmp_path)
    draft = client.patch(url + "/correction", headers=auth_headers(admin_user), json=correction_update("sales", payload, original["version"]))
    assert draft.status_code == 200, draft.text
    assert client.post(url + "/correction/submit", headers=auth_headers(admin_user), json={"expected_version": draft.json()["version"]}).status_code == 200
    bill = db_session.get(Invoice, original["id"])
    if dependency == "payment":
        receipt = Receipt(branch_id=branch.id, customer_id=bill.buyer_customer_id, created_by_id=admin_user.id, receipt_number="R-CORRECTION", receipt_date=bill.invoice_date, currency="INR", amount=Decimal("10"))
        db_session.add(receipt)
        db_session.flush()
        db_session.add(ReceiptAllocation(receipt_id=receipt.id, invoice_id=bill.id, created_by_id=admin_user.id, amount=Decimal("10"), currency="INR"))
    elif dependency == "integration":
        db_session.add(OutboundIntegrationJob(branch_id=branch.id, invoice_id=bill.id, created_by_id=admin_user.id, provider_key="accounting", operation="invoice", idempotency_key="correction-block", payload_hash="a" * 64, request_snapshot={}))
    else:
        bill.irn = "external-registered-reference"
    db_session.commit()
    assert client.get(url + "/correction?edit=1", headers=auth_headers(admin_user)).status_code == 409
    assert client.patch(url + "/correction", headers=auth_headers(admin_user), json=correction_update("sales", payload, draft.json()["version"])).status_code == 409
    assert client.post(url + "/correction/submit", headers=auth_headers(admin_user), json={"expected_version": draft.json()["version"]}).status_code == 409
    assert client.post(url + "/correction/approve", headers=auth_headers(admin_user), json={"expected_version": draft.json()["version"]}).status_code == 409


@pytest.mark.parametrize("kind", DOCUMENTS)
def test_corrections_cannot_renumber_or_apply_invalid_decimal_fields(
    kind, client, auth_headers, admin_user, branch, db_session, monkeypatch, tmp_path,
):
    url, original, payload, _, _, _ = confirmed(kind, client, auth_headers, admin_user, admin_user, branch, db_session, monkeypatch, tmp_path)
    update = correction_update(kind, payload, original["version"])
    if "purchase-orders" in url:
        update["reagent_details" if kind == "reagent_po" else "domestic_details"]["purchase_order_number"] = "CHANGED-NUMBER"
    else:
        update["invoice_number_suffix"] = "CHANGED-NUMBER"
    assert client.patch(url + "/correction", headers=auth_headers(admin_user), json=update).status_code == 409
    update = correction_update(kind, payload, original["version"])
    fields = update["reagent_details" if kind == "reagent_po" else "domestic_details"] if "purchase-orders" in url else update
    fields["lines"][0]["quantity"] = "1.0004"
    invalid = client.patch(url + "/correction", headers=auth_headers(admin_user), json=update)
    assert invalid.status_code == 422, invalid.text
    assert client.get(url, headers=auth_headers(admin_user)).json() == original


@pytest.mark.parametrize("kind", DOCUMENTS)
def test_manager_cannot_approve_own_correction_and_admin_can_return_then_approve(
    kind, client, auth_headers, admin_user, manager_user, branch, db_session, monkeypatch, tmp_path,
):
    url, original, payload, _, _, _ = confirmed(kind, client, auth_headers, admin_user, admin_user, branch, db_session, monkeypatch, tmp_path)
    response = client.patch(url + "/correction", headers=auth_headers(manager_user), json=correction_update(kind, payload, original["version"]))
    assert response.status_code == 200, response.text
    version = response.json()["version"]
    assert client.post(url + "/correction/submit", headers=auth_headers(manager_user), json={"expected_version": version}).status_code == 200
    assert client.post(url + "/correction/approve", headers=auth_headers(manager_user), json={"expected_version": version}).status_code == 403
    returned = client.post(url + "/correction/return", headers=auth_headers(admin_user), json={"expected_version": version, "reason": "Review the corrected quantity"})
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "draft"
    assert returned.json()["version"] == version + 1
    assert client.get(url, headers=auth_headers(admin_user)).json() == original
    assert client.post(url + "/correction/submit", headers=auth_headers(manager_user), json={"expected_version": version}).status_code == 409
    assert client.post(url + "/correction/submit", headers=auth_headers(manager_user), json={"expected_version": version + 1}).status_code == 200
    assert client.post(url + "/correction/approve", headers=auth_headers(admin_user), json={"expected_version": version + 1}).status_code == 200


@pytest.mark.parametrize("kind", DOCUMENTS)
def test_deleting_a_bill_also_removes_its_unconfirmed_correction(
    kind, client, auth_headers, admin_user, branch, db_session, monkeypatch, tmp_path,
):
    url, original, payload, _, _, _ = confirmed(kind, client, auth_headers, admin_user, admin_user, branch, db_session, monkeypatch, tmp_path)
    assert client.patch(url + "/correction", headers=auth_headers(admin_user), json=correction_update(kind, payload, original["version"])).status_code == 200
    assert db_session.scalar(select(func.count()).select_from(BillCorrection)) == 1
    number = original.get("invoice_number") or original["purchase_order_number"]
    response = client.request("DELETE", url, headers=auth_headers(admin_user), json={"expected_version": original["version"], "confirmation_number": number, "document_type": original["document_type"]})
    assert response.status_code == 204, response.text
    assert db_session.scalar(select(func.count()).select_from(BillCorrection)) == 0


@pytest.mark.parametrize("kind", DOCUMENTS)
def test_correction_cannot_overwrite_a_later_change_to_the_confirmed_bill(
    kind, client, auth_headers, admin_user, branch, db_session, monkeypatch, tmp_path,
):
    url, original, payload, model, _, _ = confirmed(kind, client, auth_headers, admin_user, admin_user, branch, db_session, monkeypatch, tmp_path)
    saved = client.patch(url + "/correction", headers=auth_headers(admin_user), json=correction_update(kind, payload, original["version"]))
    assert saved.status_code == 200, saved.text
    assert client.post(url + "/correction/submit", headers=auth_headers(admin_user), json={"expected_version": saved.json()["version"]}).status_code == 200
    bill = db_session.get(model, original["id"])
    bill.version += 1
    db_session.commit()
    conflict = client.post(url + "/correction/approve", headers=auth_headers(admin_user), json={"expected_version": saved.json()["version"]})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "version_conflict"
    assert client.get(url, headers=auth_headers(admin_user)).json()["final_total"] == original["final_total"]


@pytest.mark.parametrize("kind", ("domestic_oils", "reagent_po"))
def test_po_correction_does_not_refresh_saved_supplier_details_or_tax_state_from_master(
    kind, client, auth_headers, admin_user, branch, db_session, monkeypatch, tmp_path,
):
    url, original, payload, _, _, _ = confirmed(kind, client, auth_headers, admin_user, admin_user, branch, db_session, monkeypatch, tmp_path)
    master = db_session.get(Supplier, original["supplier_id"])
    master.name = "Changed master supplier"
    master.address_line1 = "Changed master street"
    master.phone = "9000012345"
    master.email = "changed@example.com"
    master.state_code = "29"
    master.state = "Karnataka"
    db_session.commit()
    details = deepcopy(payload)
    details.pop("supplier", None)
    details["supplier_id"] = original["supplier_id"]
    details["payment_terms"] = "Corrected terms only"
    response = client.patch(url + "/correction", headers=auth_headers(admin_user), json={"expected_version": original["version"], "correction_reason": "Correct payment terms", "reagent_details" if kind == "reagent_po" else "domestic_details": details})
    assert response.status_code == 200, response.text
    view = response.json()
    for field in ("supplier_name", "supplier_address_line1", "supplier_state_code", "supplier_phone", "supplier_email", "cgst_amount", "sgst_amount", "igst_amount", "final_total"):
        assert view[field] == original[field], field
    assert client.get(url, headers=auth_headers(admin_user)).json() == original


@pytest.mark.parametrize("kind", ("sales", "reagent_bill"))
def test_long_correction_reason_keeps_full_audit_without_overflowing_short_invoice_notes(
    kind, client, auth_headers, admin_user, branch, db_session, monkeypatch, tmp_path,
):
    url, original, payload, _, _, _ = confirmed(kind, client, auth_headers, admin_user, admin_user, branch, db_session, monkeypatch, tmp_path)
    reason = "Correct entered quantity. " * 70
    saved = client.patch(url + "/correction", headers=auth_headers(admin_user), json=correction_update(kind, payload, original["version"], correction_reason=reason))
    assert saved.status_code == 200, saved.text
    version = saved.json()["version"]
    assert client.post(url + "/correction/submit", headers=auth_headers(admin_user), json={"expected_version": version}).status_code == 200
    assert client.post(url + "/correction/approve", headers=auth_headers(admin_user), json={"expected_version": version}).status_code == 200
    notes = db_session.scalars(select(InvoiceAuditLog).where(InvoiceAuditLog.invoice_id == original["id"])).all()
    assert all(len(note.note or "") <= 255 for note in notes)
    audit = db_session.scalar(select(SecurityAudit).where(SecurityAudit.action == "bill_correction_confirmed").order_by(SecurityAudit.id.desc()))
    assert audit.after["reason"] == reason.strip()
    assert audit.after["snapshot"]["document"]["status"] == "approved"
    assert audit.after["snapshot"]["document"]["version"] == db_session.get(Invoice, original["id"]).version


@pytest.mark.parametrize("kind", DOCUMENTS)
def test_stale_correction_can_be_explicitly_restarted_without_losing_its_audit_or_changing_the_bill(
    kind, client, auth_headers, admin_user, staff_user, branch, db_session, monkeypatch, tmp_path,
):
    url, original, payload, model, _, _ = confirmed(kind, client, auth_headers, admin_user, admin_user, branch, db_session, monkeypatch, tmp_path)
    saved = client.patch(url + "/correction", headers=auth_headers(staff_user), json=correction_update(kind, payload, original["version"]))
    assert saved.status_code == 200, saved.text
    bill = db_session.get(model, original["id"])
    bill.version += 1
    db_session.commit()
    current = client.get(url, headers=auth_headers(admin_user)).json()
    blocked = client.get(url + "/correction?edit=1", headers=auth_headers(admin_user))
    assert blocked.status_code == 409
    detail = blocked.json()["detail"]
    assert detail["correction_base_changed"] is True
    assert detail["current_version"] == current["version"]
    assert detail["correction_version"] == saved.json()["version"]
    request = {"expected_version": current["version"], "correction_version": saved.json()["version"], "reason": "Restart against the changed confirmed bill"}
    assert client.post(url + "/correction/restart", headers=auth_headers(staff_user), json=request).status_code == 403
    stale = {**request, "expected_version": current["version"] - 1}
    assert client.post(url + "/correction/restart", headers=auth_headers(admin_user), json=stale).status_code == 409
    restarted = client.post(url + "/correction/restart", headers=auth_headers(admin_user), json=request)
    assert restarted.status_code == 200, restarted.text
    assert restarted.json()["status"] == "draft"
    assert restarted.json()["correction"]["base_version"] == current["version"]
    assert restarted.json()["correction"]["reason"] == request["reason"]
    assert restarted.json()["lines"][0]["quantity"] == original["lines"][0]["quantity"]
    assert restarted.json()["version"] > saved.json()["version"]
    assert client.get(url, headers=auth_headers(admin_user)).json() == current
    audit = db_session.scalar(select(SecurityAudit).where(SecurityAudit.action == "bill_correction_restarted").order_by(SecurityAudit.id.desc()))
    assert audit.before["working"]["lines"][0]["quantity"] == "2.000"
