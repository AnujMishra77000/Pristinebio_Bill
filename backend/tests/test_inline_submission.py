"""Inline submission contracts, using only the disposable SQLite fixture."""

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import subprocess

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.company import Branch, Company
from app.models.invoice import Invoice, InvoiceAuditLog, InvoiceLine, InvoiceRevision
from app.models.master_records import Customer, Manufacturer, Product, Purchaser, Supplier
from app.models.purchase_order import PurchaseOrder, PurchaseOrderAuditLog, PurchaseOrderLine, PurchaseOrderRevision
from app.services.invoice_pdf import (
    COPY_LABELS, PdfGenerationResult, PURCHASE_ORDER_TEMPLATE_VERSION,
    REAGENT_BILL_TEMPLATE_VERSION, REAGENT_PURCHASE_ORDER_TEMPLATE_VERSION, TEMPLATE_VERSION,
    build_invoice_html,
)
from tests.test_financial_correctness import _address, _invoice_payload, _purchase_order_payload
from tests.test_reagent_purchase_orders import _reagent_payload


DOCUMENTS = ("sales", "reagent_bill", "domestic_oils", "reagent_po")
BILLING_MODELS = (
    Company, Branch, Customer, Supplier, Purchaser, Product, Manufacturer,
    Invoice, InvoiceLine, InvoiceRevision, InvoiceAuditLog,
    PurchaseOrder, PurchaseOrderLine, PurchaseOrderRevision, PurchaseOrderAuditLog,
)


def _state(db, models=BILLING_MODELS):
    return deepcopy({
        model.__tablename__: [dict(row) for row in db.execute(select(model.__table__).order_by(*model.__table__.primary_key.columns)).mappings()]
        for model in models
    })


def _document(document_type, client, auth_headers, user, branch):
    if document_type == "reagent_po":
        payload = _reagent_payload(client, auth_headers, user, branch)
    elif document_type == "domestic_oils":
        payload = _purchase_order_payload(branch)
        payload["purchaser"] = {"name": "Draft Purchaser", "address": _address("Purchaser", address_line1="Transaction delivery street")}
    else:
        payload = _invoice_payload(branch)
        if document_type == "reagent_bill":
            reagent = _reagent_payload(client, auth_headers, user, branch)
            payload.update(document_type="reagent", lines=reagent["lines"])
    collection = "purchase-orders" if document_type in ("domestic_oils", "reagent_po") else "invoices"
    response = client.post(f"/api/v1/{collection}", headers=auth_headers(user), json=payload)
    assert response.status_code == 201, response.text
    return f"/api/v1/{collection}/{response.json()['id']}", response.json(), payload


@pytest.mark.parametrize("document_type", DOCUMENTS)
@pytest.mark.parametrize("stored_pdf", [False, True])
def test_pdf_preview_returns_inline_bytes_from_saved_snapshot_without_any_billing_writes(
    document_type, stored_pdf, client, auth_headers, staff_user, branch, db_session, monkeypatch, tmp_path,
):
    url, document, _ = _document(document_type, client, auth_headers, staff_user, branch)
    model = PurchaseOrder if "purchase-orders" in url else Invoice
    stored = db_session.get(model, document["id"])
    if stored_pdf:
        stored.pdf_storage_key = "historical.pdf"
        stored.pdf_sha256 = "a" * 64
        stored.pdf_template_version = "historical-version"
        stored.pdf_generated_by_id = staff_user.id
        stored.pdf_generated_at = datetime(2026, 9, 1, tzinfo=UTC)
    # Change masters after saving: the preview must still use transaction parties/lines.
    db_session.get(Product, stored.lines[0].product_id).name = "Changed catalog name"
    party = db_session.get(Supplier if model is PurchaseOrder else Customer, stored.supplier_id if model is PurchaseOrder else stored.buyer_customer_id)
    party.name = "Changed master party"
    db_session.commit()
    headers = auth_headers(staff_user)
    before = _state(db_session)
    pdf = b"%PDF-inline-preview"
    contexts = []

    def renderer(context):
        contexts.append(context)
        html = build_invoice_html(context)
        assert "Changed catalog name" not in html
        assert "Changed master party" not in html
        rendered_party = document.get("supplier_name") or document["buyer_name"]
        assert rendered_party in html
        if document_type == "reagent_po":
            assert context.buyer.heading == "Seller"
            assert context.buyer.name == document["supplier_name"]
            assert context.consignee.name == document["supplier_name"]
        assert document["lines"][0]["product_name"] in html
        assert context.final_total == Decimal(document["final_total"])
        return PdfGenerationResult(pdf, hashlib.sha256(pdf).hexdigest())

    def forbidden_write(*args, **kwargs):
        pytest.fail("PDF preview attempted to persist a file")

    module = "purchase_orders" if model is PurchaseOrder else "invoices"
    monkeypatch.setattr(f"app.api.v1.{module}.{'render_purchase_order_pdf' if model is PurchaseOrder else 'render_invoice_pdf'}", renderer)
    monkeypatch.setattr(f"app.api.v1.{module}._write_pdf_bytes", forbidden_write)
    monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(tmp_path / "storage-must-not-exist"))
    response = client.post(url + "/preview-pdf", headers=headers, json={"expected_version": document["version"]})
    assert response.status_code == 200, response.text
    assert response.content == pdf
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].startswith("inline;")
    expected_version = {"sales": TEMPLATE_VERSION, "reagent_bill": REAGENT_BILL_TEMPLATE_VERSION, "domestic_oils": PURCHASE_ORDER_TEMPLATE_VERSION, "reagent_po": REAGENT_PURCHASE_ORDER_TEMPLATE_VERSION}[document_type]
    assert contexts[0].template_version == expected_version
    assert contexts[0].copy_labels == (("Purchase Order",) if document_type == "domestic_oils" else COPY_LABELS)
    assert _state(db_session) == before
    assert list(tmp_path.iterdir()) == []
    # Preview does not make a final PDF downloadable.
    if not stored_pdf:
        assert client.get(url + "/pdf", headers=headers).status_code == 404


@pytest.mark.parametrize("document_type", DOCUMENTS)
@pytest.mark.parametrize("body,expected_status", [({}, 422), ({"expected_version": None}, 422), ({"expected_version": 0}, 422), ({"expected_version": True}, 422), ({"expected_version": "1"}, 422), ({"expected_version": 2}, 409)])
def test_pdf_preview_requires_exact_integer_version_before_rendering(
    document_type, body, expected_status, client, auth_headers, staff_user, branch, db_session, monkeypatch,
):
    url, _, _ = _document(document_type, client, auth_headers, staff_user, branch)
    headers = auth_headers(staff_user)
    before = _state(db_session)
    def forbidden_render(*args):
        pytest.fail("Invalid preview request reached the renderer")
    module = "purchase_orders" if "purchase-orders" in url else "invoices"
    monkeypatch.setattr(f"app.api.v1.{module}.{'render_purchase_order_pdf' if module == 'purchase_orders' else 'render_invoice_pdf'}", forbidden_render)
    response = client.post(url + "/preview-pdf", headers=headers, json=body)
    assert response.status_code == expected_status, response.text
    if expected_status == 409:
        assert response.json()["detail"]["code"] == "version_conflict"
        assert response.json()["detail"]["current_version"] == 1
    assert _state(db_session) == before


@pytest.mark.parametrize("document_type", DOCUMENTS)
def test_pdf_preview_enforces_auth_branch_access_and_missing_document(
    document_type, client, auth_headers, admin_user, staff_user, branch, other_branch,
):
    url, _, _ = _document(document_type, client, auth_headers, admin_user, other_branch)
    client.cookies.clear()
    assert client.post(url + "/preview-pdf", json={"expected_version": 1}).status_code == 401
    headers = auth_headers(staff_user)
    assert client.post(url + "/preview-pdf", headers=headers, json={"expected_version": 1}).status_code == 403
    collection = url.rsplit("/", 1)[0]
    assert client.post(collection + "/999999/preview-pdf", headers=headers, json={"expected_version": 1}).status_code == 404


@pytest.mark.parametrize("document_type", DOCUMENTS)
def test_pdf_preview_real_renderer_returns_valid_a4_pdf_without_storage(
    document_type, client, auth_headers, staff_user, branch, db_session, monkeypatch, tmp_path,
):
    url, document, _ = _document(document_type, client, auth_headers, staff_user, branch)
    headers = auth_headers(staff_user)
    before = _state(db_session)
    monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(tmp_path / "storage"))
    response = client.post(url + "/preview-pdf", headers=headers, json={"expected_version": 1})
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF-")
    info = subprocess.run(["pdfinfo", "-"], input=response.content, capture_output=True, check=True).stdout.decode()
    metadata = dict(line.split(":", 1) for line in info.splitlines() if ":" in line)
    assert "(A4)" in metadata["Page size"]
    page_count = int(metadata["Pages"].strip())
    assert page_count >= 1
    if document_type != "domestic_oils":
        assert page_count % 4 == 0
    assert _state(db_session) == before
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("state_code", ["36", "29"])
def test_domestic_totals_preview_never_writes_masters_and_matches_saved_draft(
    state_code, client, auth_headers, staff_user, branch, db_session,
):
    payload = _purchase_order_payload(branch)
    payload["supplier"]["address"] = _address("Supplier", state_code)
    payload["purchaser"] = {"name": "New Purchaser", "address": _address("New Purchaser")}
    payload["save_purchaser_for_future"] = True
    payload.update(freight_charges="1.10", packing_charges="0.20", other_charges="0.30")
    payload["lines"][0].update(quantity="3.250", rate="12.3456", other_charge="0.50")
    headers = auth_headers(staff_user)
    before = _state(db_session)
    preview = client.post("/api/v1/purchase-orders/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["taxable_value"] == "42.22"
    assert preview.json()["final_total"] == "50.00"
    assert _state(db_session) == before
    saved = client.post("/api/v1/purchase-orders", headers=headers, json=payload)
    assert saved.status_code == 201, saved.text
    for field in ("taxable_value", "cgst_amount", "sgst_amount", "igst_amount", "cess_amount", "unrounded_total", "round_off", "final_total", "amount_in_words"):
        assert saved.json()[field] == preview.json()[field]


def test_domestic_full_draft_edit_persists_snapshots_totals_number_and_revision_and_clears_pdf(
    client, auth_headers, staff_user, branch, db_session, tmp_path,
):
    url, original, payload = _document("domestic_oils", client, auth_headers, staff_user, branch)
    stored = db_session.get(PurchaseOrder, original["id"])
    stored.pdf_storage_key = "old.pdf"
    stored.pdf_sha256 = "a" * 64
    stored.pdf_template_version = "old"
    stored.pdf_generated_by_id = staff_user.id
    stored.pdf_generated_at = datetime.now(UTC)
    db_session.commit()
    masters = _state(db_session, (Supplier, Purchaser, Product))
    edited = deepcopy(payload)
    edited.update(purchase_order_number=" EDITED/PO/1 ", order_date="2026-10-03", expected_delivery_date="2026-10-08", payment_terms="Edited terms", freight_charges="1.10", packing_charges="0.20", other_charges="0.30")
    edited["supplier"].update(name="Transaction Supplier", phone="1234567890")
    edited["supplier"]["address"]["address_line1"] = "Transaction supplier street"
    edited["purchaser"].update(name="Edited Purchaser", pan="ABCDE1234F", email="edited@example.com", phone="1234567890")
    edited["purchaser"]["address"]["address_line1"] = "Edited delivery street"
    edited["lines"][0].update(quantity="3.250", rate="12.3456", description="Edited line", other_charge="0.50")
    headers = auth_headers(staff_user)
    preview = client.post("/api/v1/purchase-orders/preview", headers=headers, json=edited)
    assert preview.status_code == 200, preview.text
    response = client.patch(url, headers=headers, json={"expected_version": 1, "domestic_details": edited})
    assert response.status_code == 200, response.text
    document = response.json()
    assert document["id"] == original["id"] and document["version"] == 2 and document["status"] == "draft"
    assert document["purchase_order_number"] == "EDITED/PO/1"
    assert document["order_date"] == "2026-10-03"
    assert document["expected_delivery_date"] == "2026-10-08" and document["payment_terms"] == "Edited terms"
    assert document["supplier_name"] == "Transaction Supplier" and document["supplier_address_line1"] == "Transaction supplier street"
    assert document["purchaser_name"] == "Edited Purchaser" and document["purchaser_address_line1"] == "Edited delivery street"
    assert document["purchaser_pan"] == "ABCDE1234F" and document["purchaser_email"] == "edited@example.com"
    assert document["lines"][0]["quantity"] == "3.250" and document["lines"][0]["rate"] == "12.3456"
    assert document["lines"][0]["description"] == "Edited line"
    assert document["final_total"] == "50.00"
    for field in ("taxable_value", "cgst_amount", "sgst_amount", "round_off", "final_total"):
        assert document[field] == preview.json()[field]
    for field in ("pdf_storage_key", "pdf_sha256", "pdf_template_version", "pdf_generated_by_id", "pdf_generated_at"):
        assert document[field] is None
    assert _state(db_session, (Supplier, Purchaser, Product)) == masters
    revisions = list(db_session.scalars(select(PurchaseOrderRevision).where(PurchaseOrderRevision.purchase_order_id == original["id"]).order_by(PurchaseOrderRevision.revision)))
    assert [revision.event for revision in revisions] == ["created", "draft_updated"]
    assert revisions[0].snapshot["lines"][0]["quantity"] == "1.000"
    assert revisions[1].snapshot["document"]["freight_charges"] == "1.10"
    assert revisions[1].snapshot["document"]["purchaser_email"] == "edited@example.com"
    assert revisions[1].snapshot["lines"][0]["other_charge"] == "0.50"


@pytest.mark.parametrize("invalid,expected_status", [("missing_version", 422), ("stale_version", 409), ("null_details", 422), ("wrong_type", 422), ("wrong_branch", 422), ("wrong_supplier", 422), ("discount", 422), ("conflicting_number", 422), ("duplicate_number", 409), ("both_detail_types", 422)])
def test_domestic_full_edit_rejects_invalid_requests_atomically(
    invalid, expected_status, client, auth_headers, staff_user, branch, other_branch, db_session,
):
    url, original, payload = _document("domestic_oils", client, auth_headers, staff_user, branch)
    second_payload = _purchase_order_payload(branch, supplier_name="Other Supplier", supplier_gstin="36KLMNO1234P1Z5")
    second_payload["purchase_order_number"] = "TAKEN"
    second = client.post("/api/v1/purchase-orders", headers=auth_headers(staff_user), json=second_payload).json()
    body = {"expected_version": 1, "domestic_details": deepcopy(payload), "purchase_order_number": "ATTEMPTED"}
    if invalid == "missing_version": body.pop("expected_version")
    if invalid == "stale_version": body["expected_version"] = 2
    if invalid == "null_details": body["domestic_details"] = None
    if invalid == "wrong_type": body["domestic_details"].update(document_type="reagent", purchaser=payload["purchaser"], place_of_supply_state_code="36")
    if invalid == "wrong_branch": body["domestic_details"]["branch_id"] = other_branch.id
    if invalid == "wrong_supplier": body["domestic_details"].update(supplier=None, supplier_id=second["supplier_id"])
    if invalid == "discount": body["domestic_details"]["discount_amount"] = "1.00"
    if invalid == "conflicting_number": body["domestic_details"]["purchase_order_number"] = "OTHER"
    if invalid == "duplicate_number": body["purchase_order_number"] = "TAKEN"
    if invalid == "both_detail_types": body["reagent_details"] = payload
    headers = auth_headers(staff_user)
    before = _state(db_session)
    response = client.patch(url, headers=headers, json=body)
    assert response.status_code == expected_status, response.text
    db_session.expire_all()
    assert _state(db_session) == before


def test_domestic_preview_uses_transaction_supplier_state_when_matching_an_existing_master(
    client, auth_headers, staff_user, branch, db_session,
):
    url, original, payload = _document("domestic_oils", client, auth_headers, staff_user, branch)
    payload = deepcopy(payload)
    payload["supplier_id"] = original["supplier_id"]
    payload["supplier"]["address"] = _address("Interstate transaction", "29")
    headers = auth_headers(staff_user)
    masters = _state(db_session, (Supplier, Purchaser, Product))
    preview = client.post("/api/v1/purchase-orders/preview", headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["igst_amount"] == "18.00"
    assert preview.json()["cgst_amount"] == preview.json()["sgst_amount"] == "0.00"
    assert _state(db_session, (Supplier, Purchaser, Product)) == masters
    updated = client.patch(url, headers=headers, json={"expected_version": 1, "domestic_details": payload})
    assert updated.status_code == 200, updated.text
    assert updated.json()["supplier_state_code"] == "29"
    assert updated.json()["igst_amount"] == "18.00"
    assert _state(db_session, (Supplier, Purchaser, Product)) == masters
    saved = client.post("/api/v1/purchase-orders", headers=headers, json=payload)
    assert saved.status_code == 201, saved.text
    assert saved.json()["igst_amount"] == preview.json()["igst_amount"]


def test_domestic_amendment_full_edit_requires_fresh_approval_and_preserves_issued_number_and_old_file(
    client, auth_headers, staff_user, manager_user, branch, db_session, tmp_path,
):
    url, original, payload = _document("domestic_oils", client, auth_headers, staff_user, branch)
    headers = auth_headers(staff_user)
    assert client.post(url + "/submit", headers=headers, json={"expected_version": 1}).status_code == 200
    assert client.post(url + "/approve", headers=auth_headers(manager_user), json={"expected_version": 1}).status_code == 200
    old_file = tmp_path / "historical.pdf"
    old_file.write_bytes(b"%PDF-historical")
    stored = db_session.get(PurchaseOrder, original["id"])
    stored.pdf_storage_key = old_file.name
    db_session.commit()
    amended = client.post(url + "/amend", headers=headers, json={"expected_version": 1, "reason": "Correct draft quantity"})
    assert amended.status_code == 200
    payload = deepcopy(payload)
    payload["purchase_order_number"] = original["purchase_order_number"]
    payload["lines"][0]["quantity"] = "2.000"
    updated = client.patch(url, headers=headers, json={"expected_version": 2, "domestic_details": payload})
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "amendment_pending" and updated.json()["version"] == 3
    assert updated.json()["final_total"] == "236.00" and updated.json()["pdf_storage_key"] is None
    assert old_file.read_bytes() == b"%PDF-historical"
    attempted_renumber = client.patch(url, headers=headers, json={"expected_version": 3, "domestic_details": {**payload, "purchase_order_number": "NEW-ISSUED-NUMBER"}})
    assert attempted_renumber.status_code == 409
    assert client.post(url + "/approve", headers=auth_headers(manager_user), json={"expected_version": 3}).status_code == 409
    assert client.post(url + "/submit", headers=headers, json={"expected_version": 3}).status_code == 200
    assert client.post(url + "/approve", headers=auth_headers(manager_user), json={"expected_version": 2}).status_code == 409
    approved = client.post(url + "/approve", headers=auth_headers(manager_user), json={"expected_version": 3})
    assert approved.status_code == 200 and approved.json()["approved_revision"] == 3
    assert approved.json()["purchase_order_number"] == original["purchase_order_number"]
    revisions = list(db_session.scalars(select(PurchaseOrderRevision).where(PurchaseOrderRevision.purchase_order_id == original["id"]).order_by(PurchaseOrderRevision.revision)))
    assert revisions[1].snapshot["document"]["pdf_storage_key"] == "historical.pdf"
    assert revisions[2].snapshot["document"]["final_total"] == "236.00"


@pytest.mark.parametrize("document_type", DOCUMENTS)
@pytest.mark.parametrize("creator_role", ["staff", "manager", "admin"])
def test_inline_submission_preserves_approval_roles_and_financial_immutability(
    document_type, creator_role, client, auth_headers, staff_user, manager_user, admin_user, branch,
):
    creator = {"staff": staff_user, "manager": manager_user, "admin": admin_user}[creator_role]
    url, document, payload = _document(document_type, client, auth_headers, creator, branch)
    version = {"expected_version": document["version"]}
    headers = auth_headers(creator)
    assert client.post(url + "/approve", headers=headers, json=version).status_code == (403 if creator_role == "staff" else 409)
    assert client.post(url + "/submit", headers=headers, json=version).status_code == 200
    own_approval = client.post(url + "/approve", headers=headers, json=version)
    assert own_approval.status_code == (200 if creator_role == "admin" else 403)
    if creator_role != "admin":
        reviewer = manager_user if creator_role == "staff" else admin_user
        approved = client.post(url + "/approve", headers=auth_headers(reviewer), json=version)
        assert approved.status_code == 200, approved.text
    update = {**version, "lines": payload["lines"]} if "invoices" in url else {**version, "domestic_details" if document_type == "domestic_oils" else "reagent_details": payload}
    assert client.patch(url, headers=headers, json=update).status_code == 409
