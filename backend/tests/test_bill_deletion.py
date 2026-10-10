from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.models.authentication import SecurityAudit
from app.models.invoice import Invoice, InvoiceCreationRequest, InvoiceLine, InvoiceRevision
from app.models.integration import OutboundIntegrationJob
from app.models.master_records import Customer, Product, Supplier
from app.models.payment import Receipt, ReceiptAllocation
from app.models.purchase_order import PurchaseOrder, PurchaseOrderCreationRequest, PurchaseOrderLine, PurchaseOrderRevision
from tests.test_financial_correctness import _invoice_payload, _purchase_order_payload
from tests.test_reagent_purchase_orders import _reagent_payload
from app.services.invoice_pdf import PdfGenerationResult

KINDS = ("sales", "purchase", "reagent", "reagent-purchase")


@pytest.fixture(autouse=True)
def isolated_pdf_storage(tmp_path, monkeypatch):
    # Every deletion check, including no-file drafts, uses disposable storage.
    storage = tmp_path / "bill-pdfs"
    storage.mkdir()
    monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(storage))


def create_bill(kind, client, auth_headers, user, branch):
    collection = "invoices" if kind in ("sales", "reagent") else "purchase-orders"
    if kind == "reagent-purchase":
        payload = _reagent_payload(client, auth_headers, user, branch)
    elif collection == "purchase-orders":
        payload = _purchase_order_payload(branch)
    else:
        payload = _invoice_payload(branch)
        if kind == "reagent":
            manufacturer = client.post("/api/v1/manufacturers", headers=auth_headers(user),
                                       json={"branch_id": branch.id, "code": "MRK", "name": "Merck", "is_active": True}).json()
            payload.update(document_type="reagent")
            payload["lines"][0].update(manufacturer_id=manufacturer["id"], unit="g", gst_rate="5.00")
    headers = {**auth_headers(user), "Idempotency-Key": f"delete-test-{kind}"}
    response = client.post(f"/api/v1/{collection}", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    bill = response.json()
    request = {"expected_version": bill["version"], "confirmation_number": bill.get("invoice_number", bill.get("purchase_order_number")) or f"Draft #{bill['id']}",
               "document_type": bill["document_type"]}
    return collection, bill, payload, headers, request


@pytest.mark.parametrize('kind', KINDS)
def test_admin_can_reuse_generated_deleted_bill_number_as_a_new_save(
    kind, client, auth_headers, admin_user, branch, db_session, monkeypatch
):
    collection, original, payload, old_headers, _ = create_bill(kind, client, auth_headers, admin_user, branch)
    model = Invoice if collection == 'invoices' else PurchaseOrder
    number_field = 'invoice_number' if collection == 'invoices' else 'purchase_order_number'
    number = original[number_field]
    # Keep a higher live ID so SQLite also models PostgreSQL's non-reused IDs.
    unaffected_payload = {**payload, 'invoice_number_suffix' if collection == 'invoices' else 'purchase_order_number': 'UNRELATED-REUSE'}
    unaffected = client.post(f'/api/v1/{collection}', headers=auth_headers(admin_user), json=unaffected_payload)
    assert unaffected.status_code == 201, unaffected.text

    fixture_bytes = b'%PDF-1.4\nIsolated lifecycle fixture'
    result = PdfGenerationResult(fixture_bytes, hashlib.sha256(fixture_bytes).hexdigest())
    monkeypatch.setattr('app.api.v1.invoices.render_invoice_pdf', lambda context: result)
    monkeypatch.setattr('app.api.v1.purchase_orders.render_purchase_order_pdf', lambda context: result)
    url = f'/api/v1/{collection}/{original["id"]}'
    for action in ('submit', 'approve'):
        response = client.post(f'{url}/{action}', headers=auth_headers(admin_user), json={'expected_version': original['version']})
        assert response.status_code == 200, response.text
    generated = client.post(f'{url}/generate-pdf', headers=auth_headers(admin_user))
    assert generated.status_code == 200, generated.text
    pdf_name = generated.json()['pdf_storage_key']
    assert pdf_name
    request = {'expected_version': generated.json()['version'], 'confirmation_number': number,
               'document_type': original['document_type']}
    deleted = client.request('DELETE', url, headers=auth_headers(admin_user), json=request)
    assert deleted.status_code == 204, deleted.text
    assert client.get(url, headers=auth_headers(admin_user)).status_code == 404
    assert not Path(get_settings().pdf_storage_dir, pdf_name).exists()

    replacement_payload = {**payload, 'purchase_order_number': number} if collection == 'purchase-orders' else payload
    new_headers = {**auth_headers(admin_user), 'Idempotency-Key': f'reuse-deleted-{kind}'}
    replacement = client.post(f'/api/v1/{collection}', headers=new_headers, json=replacement_payload)
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()[number_field] == number
    assert replacement.json()['id'] != original['id']
    retry = client.post(f'/api/v1/{collection}', headers=new_headers, json=replacement_payload)
    assert retry.status_code == 200 and retry.json()['id'] == replacement.json()['id']
    duplicate = client.post(f'/api/v1/{collection}', headers={**auth_headers(admin_user), 'Idempotency-Key': f'duplicate-{kind}'}, json=replacement_payload)
    assert duplicate.status_code == 409, duplicate.text
    stale = client.post(f'/api/v1/{collection}', headers=old_headers, json=payload)
    assert stale.status_code == 410 and stale.json()['detail']['code'] == 'bill_deleted'
    assert client.get(f'/api/v1/{collection}/{unaffected.json()["id"]}', headers=auth_headers(admin_user)).status_code == 200
    assert db_session.scalar(select(func.count()).select_from(model)) == 2
    audit = db_session.scalar(select(SecurityAudit).where(SecurityAudit.action == 'bill_permanently_deleted'))
    assert audit.before['document_number'] == number and audit.actor_id == admin_user.id


@pytest.mark.parametrize('kind', KINDS)
def test_deleted_save_key_explains_how_to_create_a_new_bill_with_reusable_number(
    kind, client, auth_headers, admin_user, branch
):
    collection, bill, payload, headers, request = create_bill(kind, client, auth_headers, admin_user, branch)
    result = client.request('DELETE', f'/api/v1/{collection}/{bill["id"]}', headers=auth_headers(admin_user), json=request)
    assert result.status_code == 204, result.text
    response = client.post(f'/api/v1/{collection}', headers=headers, json=payload)
    assert response.status_code == 410
    assert 'new bill' in response.json()['detail']['message'].lower()


@pytest.mark.parametrize("kind", KINDS)
def test_permanent_delete_removes_bill_children_referenced_pdfs_but_not_masters_or_unreferenced_files(
    kind, client, auth_headers, admin_user, branch, db_session, tmp_path, monkeypatch
):
    db_session.execute(text("PRAGMA foreign_keys=ON"))
    collection, bill, payload, headers, request = create_bill(kind, client, auth_headers, admin_user, branch)
    model, line_model, revision_model = (Invoice, InvoiceLine, InvoiceRevision) if collection == "invoices" else (PurchaseOrder, PurchaseOrderLine, PurchaseOrderRevision)
    stored = db_session.get(model, bill["id"])
    # Cover finalized data without invoking/proposing PDF renderer changes.
    stored.status = "pdf_generated" if collection == "invoices" else "approved"
    prefix = "invoice" if collection == "invoices" else "purchase-order"
    current = tmp_path / f"{prefix}-{stored.id}-{'a' * 16}.pdf"
    archived = tmp_path / f"{prefix}-{stored.id}-{'b' * 16}.pdf"
    unrelated = tmp_path / f"{prefix}-{stored.id + 1}-{'a' * 16}.pdf"
    for path in (current, archived, unrelated): path.write_bytes(b"isolated PDF fixture")
    stored.pdf_storage_key = current.name
    db_session.commit()
    monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(tmp_path))
    master_counts = [db_session.scalar(select(func.count()).select_from(value)) for value in (Customer, Product, Supplier)]
    url = f"/api/v1/{collection}/{stored.id}"
    result = client.request("DELETE", url, headers=auth_headers(admin_user), json=request)
    assert result.status_code == 204, result.text
    assert result.content == b""
    assert client.get(url, headers=auth_headers(admin_user)).status_code == 404
    assert db_session.scalar(select(func.count()).select_from(model)) == 0
    assert db_session.scalar(select(func.count()).select_from(line_model)) == 0
    assert db_session.scalar(select(func.count()).select_from(revision_model)) == 0
    assert not current.exists() and archived.exists() and unrelated.exists()
    assert [db_session.scalar(select(func.count()).select_from(value)) for value in (Customer, Product, Supplier)] == master_counts
    audit = db_session.scalar(select(SecurityAudit).where(SecurityAudit.action == "bill_permanently_deleted"))
    assert audit.actor_id == admin_user.id and audit.created_at is not None
    assert audit.before["document_number"] == request["confirmation_number"]
    assert audit.before["document_type"] == request["document_type"]
    assert audit.after == {"deleted": True, "pdf_cleanup_pending": []}
    assert "buyer" not in str(audit.before).lower() and "address" not in str(audit.before).lower()
    retry = client.request("DELETE", url, headers=auth_headers(admin_user), json=request)
    assert retry.status_code == 204, retry.text
    assert db_session.scalar(select(func.count()).select_from(SecurityAudit).where(SecurityAudit.action == "bill_permanently_deleted")) == 1
    replay = client.post(f"/api/v1/{collection}", headers=headers, json=payload)
    assert replay.status_code == 410, replay.text
    assert replay.json()["detail"]["code"] == "bill_deleted"
    assert db_session.scalar(select(func.count()).select_from(model)) == 0
    creation_model = InvoiceCreationRequest if collection == "invoices" else PurchaseOrderCreationRequest
    tombstone = db_session.scalar(select(creation_model))
    assert tombstone.deleted_at is not None
    assert (tombstone.invoice_id if collection == "invoices" else tombstone.purchase_order_id) is None
    register = client.get(f"/api/v1/{collection}/register?document_type={request['document_type']}", headers=auth_headers(admin_user))
    assert register.json()["total"] == 0
    dashboard = client.get("/api/v1/dashboard", headers=auth_headers(admin_user)).json()
    count_key = {"sales": "sales_invoice_count", "purchase": "domestic_oils_purchase_order_count", "reagent": "reagent_invoice_count", "reagent-purchase": "reagent_purchase_order_count"}[kind]
    assert dashboard[count_key] == 0


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("role", ["staff", "manager"])
def test_non_admin_cannot_delete_bill(kind, role, client, auth_headers, admin_user, staff_user, manager_user, branch, db_session):
    collection, bill, _, _, request = create_bill(kind, client, auth_headers, admin_user, branch)
    result = client.request("DELETE", f"/api/v1/{collection}/{bill['id']}", headers=auth_headers(staff_user if role == "staff" else manager_user), json=request)
    assert result.status_code == 403, result.text
    assert client.get(f"/api/v1/{collection}/{bill['id']}", headers=auth_headers(admin_user)).status_code == 200
    assert db_session.scalar(select(func.count()).select_from(SecurityAudit).where(SecurityAudit.action == "bill_permanently_deleted")) == 0


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("change", [{"expected_version": 99}, {"confirmation_number": "WRONG-NUMBER"}, {"document_type": "sales"}])
def test_delete_requires_exact_reviewed_version_number_and_register(kind, change, client, auth_headers, admin_user, branch):
    collection, bill, _, _, request = create_bill(kind, client, auth_headers, admin_user, branch)
    if change == {"document_type": "sales"} and request["document_type"] == "sales": change = {"document_type": "reagent"}
    result = client.request("DELETE", f"/api/v1/{collection}/{bill['id']}", headers=auth_headers(admin_user), json={**request, **change})
    assert result.status_code == 409, result.text
    assert client.get(f"/api/v1/{collection}/{bill['id']}", headers=auth_headers(admin_user)).status_code == 200


@pytest.mark.parametrize("field,value", [("expected_version", None), ("expected_version", 0), ("expected_version", True), ("confirmation_number", None), ("confirmation_number", "   "), ("document_type", "unknown")])
def test_delete_validation_is_clear(field, value, client, auth_headers, admin_user, branch):
    collection, bill, _, _, request = create_bill("sales", client, auth_headers, admin_user, branch)
    response = client.request("DELETE", f"/api/v1/{collection}/{bill['id']}", headers=auth_headers(admin_user), json={**request, field: value})
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"][-1] == field


@pytest.mark.parametrize("reversed_allocation", [False, True])
def test_any_payment_allocation_blocks_invoice_deletion(reversed_allocation, client, auth_headers, admin_user, branch, db_session):
    collection, bill, _, _, request = create_bill("sales", client, auth_headers, admin_user, branch)
    receipt = Receipt(branch_id=branch.id, customer_id=bill["buyer_customer_id"], created_by_id=admin_user.id,
                      receipt_number="REC-DELETE", receipt_date=datetime.now(UTC).date(), currency="INR", amount=Decimal("10.00"))
    db_session.add(receipt); db_session.flush()
    allocation = ReceiptAllocation(receipt_id=receipt.id, invoice_id=bill["id"], created_by_id=admin_user.id, amount=Decimal("10.00"), currency="INR",
                                   reversed_at=datetime.now(UTC) if reversed_allocation else None)
    db_session.add(allocation); db_session.commit()
    result = client.request("DELETE", f"/api/v1/{collection}/{bill['id']}", headers=auth_headers(admin_user), json=request)
    assert result.status_code == 409, result.text
    assert result.json()["detail"]["code"] == "bill_has_payments"
    assert db_session.get(ReceiptAllocation, allocation.id) is not None
    assert db_session.get(Invoice, bill["id"]) is not None


def test_pdf_cleanup_failure_is_retryable_not_fake_success(client, auth_headers, admin_user, branch, db_session, tmp_path, monkeypatch):
    collection, bill, payload, headers, request = create_bill("sales", client, auth_headers, admin_user, branch)
    pdf = tmp_path / f"invoice-{bill['id']}-{'a' * 16}.pdf"
    pdf.write_bytes(b"isolated PDF fixture")
    stored = db_session.get(Invoice, bill["id"]); stored.pdf_storage_key = pdf.name; db_session.commit()
    monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(tmp_path))
    from pathlib import Path
    original = Path.unlink
    def fail_unlink(path, *args, **kwargs):
        if path == pdf: raise PermissionError("Fixture denies deletion")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail_unlink)
    url = f"/api/v1/{collection}/{bill['id']}"
    response = client.request("DELETE", url, headers=auth_headers(admin_user), json=request)
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "pdf_cleanup_pending"
    assert pdf.exists()
    assert client.post(f"/api/v1/{collection}", headers=headers, json=payload).status_code == 410
    monkeypatch.setattr(Path, "unlink", original)
    response = client.request("DELETE", url, headers=auth_headers(admin_user), json=request)
    assert response.status_code == 204 and not pdf.exists()


def test_invalid_pdf_path_blocks_deletion_without_touching_external_file(client, auth_headers, admin_user, branch, db_session, tmp_path, monkeypatch):
    collection, bill, _, _, request = create_bill("sales", client, auth_headers, admin_user, branch)
    external = tmp_path / "external.pdf"; external.write_bytes(b"must remain")
    storage = tmp_path / "storage"; storage.mkdir()
    stored = db_session.get(Invoice, bill["id"]); stored.pdf_storage_key = "../external.pdf"; db_session.commit()
    monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(storage))
    response = client.request("DELETE", f"/api/v1/{collection}/{bill['id']}", headers=auth_headers(admin_user), json=request)
    assert response.status_code == 503, response.text
    assert external.read_bytes() == b"must remain"
    assert db_session.get(Invoice, bill["id"]) is not None


@pytest.mark.parametrize("job_status", ["unavailable", "queued", "accepted", "cancelled"])
def test_integration_history_always_blocks_delete(job_status, client, auth_headers, admin_user, branch, db_session):
    _, bill, _, _, request = create_bill("sales", client, auth_headers, admin_user, branch)
    job = OutboundIntegrationJob(branch_id=branch.id, invoice_id=bill["id"], created_by_id=admin_user.id,
                                 provider_key="fixture-accounting", operation="invoice_submission", idempotency_key="retain-job",
                                 payload_hash="a" * 64, status=job_status, request_snapshot={"invoice_id": bill["id"]})
    db_session.add(job); db_session.commit()
    response = client.request("DELETE", f"/api/v1/invoices/{bill['id']}", headers=auth_headers(admin_user), json=request)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "bill_has_integrations"
    assert db_session.get(OutboundIntegrationJob, job.id).status == job_status
    assert db_session.get(Invoice, bill["id"]) is not None


def test_database_failure_preserves_bill_and_pdf(client, auth_headers, admin_user, branch, db_session, tmp_path, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    _, bill, _, _, request = create_bill("sales", client, auth_headers, admin_user, branch)
    pdf = tmp_path / f"invoice-{bill['id']}-{'a' * 16}.pdf"; pdf.write_bytes(b"must remain")
    stored = db_session.get(Invoice, bill["id"]); stored.pdf_storage_key = pdf.name; db_session.commit()
    monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(tmp_path))
    headers = auth_headers(admin_user)
    original = db_session.commit
    def conflict_commit():
        if any(isinstance(item, Invoice) for item in db_session.deleted):
            raise IntegrityError("DELETE fixture", {}, Exception("new foreign key reference"))
        return original()
    monkeypatch.setattr(db_session, "commit", conflict_commit)
    response = client.request("DELETE", f"/api/v1/invoices/{bill['id']}", headers=headers, json=request)
    assert response.status_code == 409, response.text
    assert pdf.read_bytes() == b"must remain"
    assert db_session.get(Invoice, bill["id"]) is not None
    assert db_session.scalar(select(func.count()).select_from(SecurityAudit).where(SecurityAudit.action == "bill_permanently_deleted")) == 0
    assert db_session.scalar(select(InvoiceCreationRequest)).deleted_at is None


def test_shared_pdf_reference_cannot_erase_other_bill(client, auth_headers, admin_user, branch, db_session, tmp_path, monkeypatch):
    _, bill, _, _, request = create_bill("sales", client, auth_headers, admin_user, branch)
    response = client.post("/api/v1/invoices", headers=auth_headers(admin_user), json=_invoice_payload(branch))
    other_id = response.json()["id"]
    pdf = tmp_path / "legacy-shared.pdf"; pdf.write_bytes(b"shared historical bytes")
    for invoice_id in (bill["id"], other_id): db_session.get(Invoice, invoice_id).pdf_storage_key = pdf.name
    db_session.commit(); monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(tmp_path))
    response = client.request("DELETE", f"/api/v1/invoices/{bill['id']}", headers=auth_headers(admin_user), json=request)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "shared_pdf_reference"
    assert pdf.exists()
    assert db_session.scalar(select(func.count()).select_from(Invoice)) == 2


def test_deleted_bill_key_still_conflicts_on_changed_payload(client, auth_headers, admin_user, branch):
    collection, bill, payload, headers, request = create_bill("sales", client, auth_headers, admin_user, branch)
    url = f"/api/v1/{collection}/{bill['id']}"
    assert client.request("DELETE", url, headers=auth_headers(admin_user), json=request).status_code == 204
    response = client.post(f"/api/v1/{collection}", headers=headers, json={**payload, "payment_terms": "Changed intent"})
    assert response.status_code == 409


def test_delete_missing_bill_and_hostile_csrf_are_rejected(client, auth_headers, admin_user):
    request = {"expected_version": 1, "confirmation_number": "MISSING", "document_type": "sales"}
    headers = auth_headers(admin_user)
    assert client.request("DELETE", "/api/v1/invoices/9999", headers=headers, json=request).status_code == 404
    hostile = client.raw_request("DELETE", "/api/v1/invoices/9999", headers={**headers, "Origin": "https://hostile.example"}, json=request)
    assert hostile.status_code == 403


@pytest.mark.parametrize("kind", ["purchase", "reagent-purchase"])
def test_revision_referenced_pdf_is_deleted_but_unreferenced_archive_is_not(kind, client, auth_headers, admin_user, branch, db_session, tmp_path, monkeypatch):
    collection, bill, _, _, request = create_bill(kind, client, auth_headers, admin_user, branch)
    archived = tmp_path / "referenced-old-revision.pdf"; archived.write_bytes(b"old revision")
    unrelated = tmp_path / f"purchase-order-{bill['id']}-{'b' * 16}.pdf"; unrelated.write_bytes(b"unreferenced; do not infer ownership")
    revision = db_session.scalar(select(PurchaseOrderRevision).where(PurchaseOrderRevision.purchase_order_id == bill["id"]))
    revision.snapshot = {**revision.snapshot, "document": {**revision.snapshot["document"], "pdf_storage_key": archived.name}}
    db_session.commit(); monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(tmp_path))
    response = client.request("DELETE", f"/api/v1/{collection}/{bill['id']}", headers=auth_headers(admin_user), json=request)
    assert response.status_code == 204, response.text
    assert not archived.exists() and unrelated.exists()


def test_symlink_pdf_is_never_followed_or_deleted(client, auth_headers, admin_user, branch, db_session, tmp_path, monkeypatch):
    _, bill, _, _, request = create_bill("sales", client, auth_headers, admin_user, branch)
    external = tmp_path / "external.pdf"; external.write_bytes(b"not owned")
    storage = tmp_path / "storage"; storage.mkdir()
    link = storage / "bill.pdf"; link.symlink_to(external)
    stored = db_session.get(Invoice, bill["id"]); stored.pdf_storage_key = link.name; db_session.commit()
    monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(storage))
    response = client.request("DELETE", f"/api/v1/invoices/{bill['id']}", headers=auth_headers(admin_user), json=request)
    assert response.status_code == 503
    assert external.read_bytes() == b"not owned" and link.is_symlink()
    assert db_session.get(Invoice, bill["id"]) is not None


def test_other_bill_revision_pdf_reference_blocks_deletion(client, auth_headers, admin_user, branch, db_session, tmp_path, monkeypatch):
    _, bill, _, _, request = create_bill("sales", client, auth_headers, admin_user, branch)
    _, other, _, _, _ = create_bill("purchase", client, auth_headers, admin_user, branch)
    pdf = tmp_path / "shared-history.pdf"; pdf.write_bytes(b"another bill's revision")
    db_session.get(Invoice, bill["id"]).pdf_storage_key = pdf.name
    revision = db_session.scalar(select(PurchaseOrderRevision).where(PurchaseOrderRevision.purchase_order_id == other["id"]))
    revision.snapshot = {**revision.snapshot, "document": {**revision.snapshot["document"], "pdf_storage_key": pdf.name}}
    db_session.commit(); monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(tmp_path))
    response = client.request("DELETE", f"/api/v1/invoices/{bill['id']}", headers=auth_headers(admin_user), json=request)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "shared_pdf_reference"
    assert pdf.read_bytes() == b"another bill's revision"


@pytest.mark.parametrize("kind", ["sales", "purchase"])
def test_stale_creation_record_observes_fresh_deletion_tombstone(kind, client, auth_headers, admin_user, branch, db_session):
    from fastapi import HTTPException
    from app.api.v1.invoices import _invoice_for_creation_request
    from app.api.v1.purchase_orders import _purchase_order_for_creation_request
    from sqlalchemy import update
    collection, bill, _, _, _ = create_bill(kind, client, auth_headers, admin_user, branch)
    creation_model = InvoiceCreationRequest if collection == "invoices" else PurchaseOrderCreationRequest
    model = Invoice if collection == "invoices" else PurchaseOrder
    link = "invoice_id" if collection == "invoices" else "purchase_order_id"
    original = db_session.scalar(select(creation_model))
    # Simulate the DB state changing after the replay loaded its ORM object.
    db_session.execute(update(creation_model).where(creation_model.id == original.id).values({link: None, "deleted_at": datetime.now(UTC)}).execution_options(synchronize_session=False))
    db_session.delete(db_session.get(model, bill["id"])); db_session.flush()
    assert original.deleted_at is None
    with pytest.raises(HTTPException) as failure:
        (_invoice_for_creation_request if collection == "invoices" else _purchase_order_for_creation_request)(db_session, original)
    assert failure.value.status_code == 410
