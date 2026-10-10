"""Company headers must not follow supplier/pickup edits or master refreshes."""
from datetime import UTC, datetime
from pathlib import Path
import runpy
import subprocess

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text

from app.models.invoice import Invoice, InvoiceRevision
from app.models.purchase_order import PurchaseOrder, PurchaseOrderRevision
from app.services.invoice_pdf import (
    build_invoice_context, build_invoice_html, build_purchase_order_context,
    build_reagent_purchase_order_context,
)
from tests.test_financial_correctness import _address, _invoice_payload, _purchase_order_payload


BILL_TYPES = ("sales", "reagent", "domestic_oils", "reagent_po")
COMPANY_ADDRESS = "10 Registered Office Road\nHyderabad, Telangana - 500010"
PICKUP_ADDRESS = "20 Supplier Warehouse, Industrial Area, Hyderabad, Telangana - 500001"
NEW_PICKUP_ADDRESS = "30 New Warehouse, Industrial Area, Hyderabad, Telangana - 500001"


def _default_supplier(client, headers, branch):
    response = client.post("/api/v1/suppliers", headers=headers, json={
        "branch_id": branch.id, "name": "Pickup Supplier",
        "address": _address("Warehouse", address_line1="20 Supplier Warehouse"),
        "is_default": True, "is_active": True,
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _payload(client, headers, branch, bill_type, supplier_id):
    if bill_type in ("sales", "reagent"):
        payload = _invoice_payload(branch)
        endpoint, model = "/api/v1/invoices", Invoice
        if bill_type == "reagent":
            payload["document_type"] = "reagent"
    else:
        payload = _purchase_order_payload(branch)
        payload.pop("supplier")
        payload["supplier_id"] = supplier_id
        endpoint, model = "/api/v1/purchase-orders", PurchaseOrder
        if bill_type == "reagent_po":
            payload.update(document_type="reagent", place_of_supply_state_code="36",
                           purchaser={"name": "Lab Purchaser", "address": _address("Lab")})
    if bill_type in ("reagent", "reagent_po"):
        manufacturer = client.post("/api/v1/manufacturers", headers=headers, json={
            "branch_id": branch.id, "code": "SIG", "name": "Sigma", "is_active": True,
        })
        assert manufacturer.status_code == 201, manufacturer.text
        payload["lines"][0].update(manufacturer_id=manufacturer.json()["id"], unit="g")
    return endpoint, model, payload


def _context(document, model, bill_type, company, branch):
    builder = build_invoice_context if model is Invoice else (
        build_reagent_purchase_order_context if bill_type == "reagent_po" else build_purchase_order_context
    )
    return builder(document, company=company, branch=branch, generated_at=datetime.now(UTC))


@pytest.mark.parametrize("bill_type", BILL_TYPES)
def test_supplier_save_changes_only_future_pickup_not_company_header(
    client, auth_headers, staff_user, branch, company, db_session, bill_type,
):
    company.registered_address = COMPANY_ADDRESS
    db_session.commit()
    headers = auth_headers(staff_user)
    supplier_id = _default_supplier(client, headers, branch)
    endpoint, model, payload = _payload(client, headers, branch, bill_type, supplier_id)
    created = client.post(endpoint, headers={**headers, "Idempotency-Key": "address-save"}, json=payload)
    assert created.status_code == 201, created.text
    document = db_session.get(model, created.json()["id"])
    context = _context(document, model, bill_type, company, branch)
    assert context.seller.address_lines == ("10 Registered Office Road", "Hyderabad, Telangana - 500010")
    assert context.seller.pickup_address == PICKUP_ADDRESS
    assert created.json()["company_registered_address"] == COMPANY_ADDRESS
    assert created.json()["pickup_address"] == PICKUP_ADDRESS

    changed = client.patch(f"/api/v1/suppliers/{supplier_id}", headers=headers,
                           json={"address": _address("Warehouse", address_line1="30 New Warehouse")})
    assert changed.status_code == 200, changed.text
    db_session.refresh(company)
    db_session.refresh(branch)
    assert company.registered_address == COMPANY_ADDRESS
    assert branch.address_line1 == "Hyderabad Branch Address"
    assert _context(document, model, bill_type, company, branch).seller.pickup_address == PICKUP_ADDRESS
    replay = client.post(endpoint, headers={**headers, "Idempotency-Key": "address-save"}, json=payload)
    assert replay.status_code == 200 and replay.json()["id"] == document.id
    assert replay.json()["pickup_address"] == PICKUP_ADDRESS

    if model is Invoice:
        payload["invoice_number_suffix"] = "ADDRESS-SECOND"
    second = client.post(endpoint, headers=headers, json=payload)
    assert second.status_code == 201, second.text
    second_context = _context(db_session.get(model, second.json()["id"]), model, bill_type, company, branch)
    assert second_context.seller.address_lines == context.seller.address_lines
    assert second_context.seller.pickup_address == NEW_PICKUP_ADDRESS
    html = build_invoice_html(second_context)
    assert html.count("10 Registered Office Road") == len(second_context.copy_labels)
    assert NEW_PICKUP_ADDRESS not in html
    assert "Pickup Address:" not in html


@pytest.mark.parametrize("bill_type", BILL_TYPES)
def test_approval_keeps_reviewed_address_snapshots_and_revision_history(
    client, auth_headers, staff_user, admin_user, branch, company, db_session, bill_type,
):
    company.registered_address = COMPANY_ADDRESS
    db_session.commit()
    headers = auth_headers(staff_user)
    supplier_id = _default_supplier(client, headers, branch)
    endpoint, model, payload = _payload(client, headers, branch, bill_type, supplier_id)
    created = client.post(endpoint, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]
    version = created.json()["version"]
    assert client.post(f"{endpoint}/{document_id}/submit", headers=headers,
                       json={"expected_version": version}).status_code == 200
    company.registered_address = "99 Later Registered Office"
    branch.address_line1 = "88 Later GST Address"
    db_session.commit()
    assert client.patch(f"/api/v1/suppliers/{supplier_id}", headers=headers,
                        json={"address": _address("Warehouse", address_line1="30 New Warehouse")}).status_code == 200
    approved = client.post(f"{endpoint}/{document_id}/approve", headers=auth_headers(admin_user),
                           json={"expected_version": version})
    assert approved.status_code == 200, approved.text
    assert approved.json()["company_registered_address"] == COMPANY_ADDRESS
    assert approved.json()["pickup_address"] == PICKUP_ADDRESS
    document = db_session.get(model, document_id)
    context = _context(document, model, bill_type, company, branch)
    assert context.seller.address_lines == ("10 Registered Office Road", "Hyderabad, Telangana - 500010")
    assert context.seller.pickup_address == PICKUP_ADDRESS
    revision_model = InvoiceRevision if model is Invoice else PurchaseOrderRevision
    fk = revision_model.invoice_id if model is Invoice else revision_model.purchase_order_id
    revision = db_session.scalar(select(revision_model).where(fk == document_id).order_by(revision_model.id))
    addresses = revision.snapshot["seller_addresses"] if model is Invoice else revision.snapshot["document"]
    assert addresses["company_registered_address"] == COMPANY_ADDRESS
    assert addresses["pickup_address"] == PICKUP_ADDRESS


@pytest.mark.parametrize("bill_type", ("domestic_oils", "reagent_po"))
def test_inline_po_pickup_edit_preserves_company_and_previous_revision(
    client, auth_headers, staff_user, branch, company, db_session, bill_type,
):
    company.registered_address = COMPANY_ADDRESS
    db_session.commit()
    headers = auth_headers(staff_user)
    supplier_id = _default_supplier(client, headers, branch)
    endpoint, model, payload = _payload(client, headers, branch, bill_type, supplier_id)
    payload["supplier"] = {"name": "Pickup Supplier", "address": _address("Warehouse", address_line1="Manual Pickup")}
    created = client.post(endpoint, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    payload["supplier"]["address"]["address_line1"] = "Edited Manual Pickup"
    details_key = "reagent_details" if bill_type == "reagent_po" else "domestic_details"
    updated = client.patch(f"{endpoint}/{created.json()['id']}", headers=headers,
                           json={"expected_version": created.json()["version"], details_key: payload})
    assert updated.status_code == 200, updated.text
    assert updated.json()["company_registered_address"] == COMPANY_ADDRESS
    assert updated.json()["pickup_address"] == "Edited Manual Pickup, Industrial Area, Hyderabad, Telangana - 500001"
    revisions = list(db_session.scalars(select(PurchaseOrderRevision).order_by(PurchaseOrderRevision.id)))
    assert revisions[0].snapshot["document"]["pickup_address"] == "Manual Pickup, Industrial Area, Hyderabad, Telangana - 500001"
    assert revisions[1].snapshot["document"]["company_registered_address"] == COMPANY_ADDRESS


@pytest.mark.parametrize("default_state", ("none", "inactive", "other_profile"))
def test_sales_pickup_never_uses_inactive_or_foreign_default_supplier(
    client, auth_headers, staff_user, admin_user, branch, other_branch, company, db_session, default_state,
):
    if default_state != "none":
        supplier_id = _default_supplier(client, auth_headers(admin_user), other_branch if default_state == "other_profile" else branch)
        if default_state == "inactive":
            assert client.patch(f"/api/v1/suppliers/{supplier_id}", headers=auth_headers(admin_user), json={"is_active": False}).status_code == 200
    created = client.post("/api/v1/invoices", headers=auth_headers(staff_user), json=_invoice_payload(branch))
    assert created.status_code == 201, created.text
    context = _context(db_session.get(Invoice, created.json()["id"]), Invoice, "sales", company, branch)
    assert context.seller.address_lines == ("1 Billing Street",)
    assert context.seller.pickup_address is None


def test_missing_registered_address_uses_stable_profile_snapshot_not_supplier(
    client, auth_headers, staff_user, branch, company, db_session,
):
    company.registered_address = None
    db_session.commit()
    headers = auth_headers(staff_user)
    _default_supplier(client, headers, branch)
    created = client.post("/api/v1/invoices", headers=headers, json=_invoice_payload(branch))
    assert created.status_code == 201, created.text
    document = db_session.get(Invoice, created.json()["id"])
    branch.address_line1 = "Changed Profile Address"
    db_session.commit()
    context = _context(document, Invoice, "sales", company, branch)
    assert context.seller.address_lines == ("Hyderabad Branch Address", "Hyderabad, Telangana - 500001")
    assert context.seller.pickup_address == PICKUP_ADDRESS


@pytest.mark.parametrize("bill_type", BILL_TYPES)
def test_legacy_address_context_is_not_reinterpreted_from_current_company(
    client, auth_headers, staff_user, branch, company, db_session, bill_type,
):
    headers = auth_headers(staff_user)
    supplier_id = _default_supplier(client, headers, branch)
    endpoint, model, payload = _payload(client, headers, branch, bill_type, supplier_id)
    created = client.post(endpoint, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    document = db_session.get(model, created.json()["id"])
    document.company_registered_address = None
    document.pickup_address = None
    document.pdf_storage_key = "historical.pdf"
    document.pdf_sha256 = "a" * 64
    db_session.commit()
    company.registered_address = "Do Not Reinterpret Historical Company Address"
    context = _context(document, model, bill_type, company, branch)
    assert context.seller.address_lines == ("Hyderabad Branch Address", "Hyderabad, Telangana - 500001")
    assert context.seller.pickup_address == "Hyderabad Branch Address, Hyderabad, Telangana - 500001"
    assert document.pdf_storage_key == "historical.pdf"
    assert document.pdf_sha256 == "a" * 64


def test_forward_address_migration_keeps_historical_rows_and_pdf_references():
    migration_path = Path(__file__).parents[1] / "alembic/versions/20261004_0020_bill_address_snapshots.py"
    migration = runpy.run_path(str(migration_path))
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        for table in ("invoices", "purchase_orders"):
            connection.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, pdf_storage_key TEXT, final_total NUMERIC(14, 2))"))
            connection.execute(text(f"INSERT INTO {table} VALUES (1, 'issued-original.pdf', 346849.00)"))
        with Operations.context(MigrationContext.configure(connection)):
            migration["upgrade"]()
        for table in ("invoices", "purchase_orders"):
            row = connection.execute(text(f"SELECT * FROM {table}")).mappings().one()
            assert row["pdf_storage_key"] == "issued-original.pdf"
            assert row["final_total"] == 346849
            assert row["company_registered_address"] is None
            assert row["pickup_address"] is None
            columns = {column["name"]: column for column in inspect(connection).get_columns(table)}
            assert columns["company_registered_address"]["nullable"]
            assert columns["pickup_address"]["nullable"]
    engine.dispose()


@pytest.mark.parametrize("bill_type", BILL_TYPES)
def test_address_pdf_preview_renders_snapshots_without_finalizing(
    client, auth_headers, staff_user, branch, company, db_session, bill_type, tmp_path,
):
    company.registered_address = COMPANY_ADDRESS
    db_session.commit()
    headers = auth_headers(staff_user)
    supplier_id = _default_supplier(client, headers, branch)
    endpoint, model, payload = _payload(client, headers, branch, bill_type, supplier_id)
    created = client.post(endpoint, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]
    response = client.post(f"{endpoint}/{document_id}/preview-pdf", headers=headers,
                           json={"expected_version": created.json()["version"]})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    pdf_path = tmp_path / f"{bill_type}-addresses.pdf"
    pdf_path.write_bytes(response.content)
    info = subprocess.run(["pdfinfo", str(pdf_path)], check=True, capture_output=True, text=True).stdout
    pages = next(int(line.split(":", 1)[1]) for line in info.splitlines() if line.startswith("Pages:"))
    assert pages == (1 if bill_type == "domestic_oils" else 4)
    subprocess.run(["pdftoppm", "-scale-to", "1400", "-png", str(pdf_path), str(tmp_path / bill_type)],
                   check=True, capture_output=True)
    assert len(list(tmp_path.glob(f"{bill_type}-*.png"))) == pages
    document = db_session.get(model, document_id)
    assert str(document.status) in ("InvoiceStatus.DRAFT", "draft")
    assert document.version == 1 and document.pdf_storage_key is None
    assert document.company_registered_address == COMPANY_ADDRESS
    assert document.pickup_address == PICKUP_ADDRESS
    print(f"Address PDF/PNG fixture: {pdf_path}")
