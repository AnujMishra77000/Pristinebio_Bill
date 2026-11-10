"""Bank maintenance must change the default consumed by new bills and POs."""
from datetime import UTC, datetime
from hashlib import sha256

import pytest
from sqlalchemy import select

from app.api.v1 import invoices, purchase_orders
from app.core.config import get_settings
from app.models.authentication import SecurityAudit
from app.models.invoice import Invoice
from app.models.master_records import BankAccount
from app.services.invoice_pdf import PdfGenerationResult, build_invoice_html
from tests.test_financial_correctness import _invoice_payload, _purchase_order_payload
from tests.test_remaining_masters import bank_account_payload


def _create_account(client, headers, branch, **updates):
    response = client.post("/api/v1/bank-accounts", headers=headers,
                           json={**bank_account_payload(branch.id), **updates})
    assert response.status_code == 201, response.text
    return response.json()


def _accounts(client, headers):
    response = client.get("/api/v1/bank-accounts", headers=headers)
    assert response.status_code == 200, response.text
    return {record["id"]: record for record in response.json()}


def test_creating_default_replaces_all_old_defaults_in_its_profile_and_audits_them(
    client, auth_headers, admin_user, branch, other_branch, db_session,
):
    headers = auth_headers(admin_user)
    first = _create_account(client, headers, branch)
    second = _create_account(client, headers, branch, is_default=False)
    unrelated = _create_account(client, headers, other_branch)
    # Simulate pre-fix data with multiple defaults, without a destructive cleanup.
    db_session.get(BankAccount, second["id"]).is_default = True
    db_session.commit()

    chosen = _create_account(client, headers, branch, account_number="000987654321")
    records = _accounts(client, headers)
    assert [row["id"] for row in records.values() if row["branch_id"] == branch.id and row["is_default"]] == [chosen["id"]]
    assert records[unrelated["id"]]["is_default"] is True
    events = list(db_session.scalars(select(SecurityAudit).where(SecurityAudit.action == "bank_account_updated")))
    assert {event.entity_id for event in events} == {str(first["id"]), str(second["id"])}
    for event in events:
        assert event.actor_id == admin_user.id
        assert event.before["is_default"] is True
        assert event.after["is_default"] is False


@pytest.mark.parametrize("move_profile", [False, True])
def test_setting_existing_account_as_default_replaces_the_destination_default(
    client, auth_headers, admin_user, branch, other_branch, move_profile,
):
    headers = auth_headers(admin_user)
    old = _create_account(client, headers, branch)
    chosen = _create_account(client, headers, other_branch if move_profile else branch, is_default=False)
    unrelated = _create_account(client, headers, other_branch)
    updates = {"is_default": True}
    if move_profile:
        updates["branch_id"] = branch.id
    response = client.patch(f"/api/v1/bank-accounts/{chosen['id']}", headers=headers, json=updates)
    assert response.status_code == 200, response.text
    records = _accounts(client, headers)
    assert records[chosen["id"]]["is_default"] is True
    assert records[old["id"]]["is_default"] is False
    assert records[unrelated["id"]]["is_default"] is True


def test_deactivation_clears_default_and_reactivation_does_not_restore_it(
    client, auth_headers, admin_user, branch,
):
    headers = auth_headers(admin_user)
    account = _create_account(client, headers, branch)
    url = f"/api/v1/bank-accounts/{account['id']}"
    deactivated = client.patch(url, headers=headers, json={"is_active": False})
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["is_default"] is False
    reactivated = client.patch(url, headers=headers, json={"is_active": True})
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["is_default"] is False


@pytest.mark.parametrize("operation", ["create", "update"])
def test_inactive_account_cannot_replace_an_active_default(
    client, auth_headers, admin_user, branch, operation,
):
    headers = auth_headers(admin_user)
    old = _create_account(client, headers, branch)
    if operation == "create":
        response = client.post("/api/v1/bank-accounts", headers=headers,
                               json={**bank_account_payload(branch.id), "is_active": False})
    else:
        inactive = _create_account(client, headers, branch, is_default=False, is_active=False)
        response = client.patch(f"/api/v1/bank-accounts/{inactive['id']}", headers=headers,
                                json={"is_default": True})
    assert response.status_code == 422, response.text
    assert _accounts(client, headers)[old["id"]]["is_default"] is True


@pytest.mark.parametrize("role", ["staff_user", "manager_user"])
def test_only_admin_can_change_default_or_bank_details(
    client, auth_headers, admin_user, branch, role, request,
):
    headers = auth_headers(admin_user)
    account = _create_account(client, headers, branch)
    denied_headers = auth_headers(request.getfixturevalue(role))
    assert client.patch(f"/api/v1/bank-accounts/{account['id']}", headers=denied_headers,
                        json={"is_default": False, "account_number": "000987654321"}).status_code == 403
    assert client.post("/api/v1/bank-accounts", headers=denied_headers,
                       json=bank_account_payload(branch.id)).status_code == 403
    assert _accounts(client, headers)[account["id"]]["account_number"] == "12345678901"


@pytest.mark.parametrize("kind", ["sales", "reagent", "purchase", "reagent_purchase"])
def test_new_bills_and_pos_use_updated_default_while_stored_final_pdfs_keep_their_bytes(
    client, auth_headers, admin_user, branch, db_session, monkeypatch, tmp_path, kind,
):
    headers = auth_headers(admin_user)
    old = _create_account(client, headers, branch)
    is_po = kind in {"purchase", "reagent_purchase"}
    payload_factory = _purchase_order_payload if is_po else _invoice_payload
    manufacturer = None
    if kind in {"reagent", "reagent_purchase"}:
        response = client.post("/api/v1/manufacturers", headers=headers, json={
            "branch_id": branch.id, "code": "BANKTEST", "name": "Test Manufacturer", "is_active": True,
        })
        assert response.status_code == 201, response.text
        manufacturer = response.json()["id"]
    collection = "/api/v1/purchase-orders" if is_po else "/api/v1/invoices"
    api = purchase_orders if is_po else invoices
    context_builder = api._purchase_order_pdf_context if is_po else api._invoice_pdf_context
    monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(tmp_path))

    def render(context):
        data = ("%PDF-1.4\n" + repr(context.bank_detail_rows)).encode()
        return PdfGenerationResult(pdf_bytes=data, sha256=sha256(data).hexdigest())

    monkeypatch.setattr(api, "render_purchase_order_pdf" if is_po else "render_invoice_pdf", render)

    def create_document():
        payload = payload_factory(branch)
        if manufacturer:
            payload.update(document_type="reagent", place_of_supply_state_code="36")
            payload["lines"][0]["manufacturer_id"] = manufacturer
        result = client.post(collection, headers=headers, json=payload)
        assert result.status_code == 201, result.text
        return result.json()

    original = create_document()
    url = f"{collection}/{original['id']}"
    for action in ("submit", "approve", "generate-pdf"):
        result = client.post(f"{url}/{action}", headers=headers,
                             json={"expected_version": original["version"]})
        assert result.status_code == 200, result.text
    final_metadata = result.json()
    final_bytes = client.get(url + "/pdf", headers=headers).content

    chosen = _create_account(client, headers, branch, is_default=False, account_number="000987654321")
    selected = client.patch(f"/api/v1/bank-accounts/{chosen['id']}", headers=headers, json={"is_default": True})
    assert selected.status_code == 200, selected.text
    updated = client.patch(f"/api/v1/bank-accounts/{chosen['id']}", headers=headers,
                           json={"account_number": "000123450000", "ifsc_code": "TEST0001234"})
    assert updated.status_code == 200, updated.text

    new = create_document()
    document = api._get_purchase_order(db_session, admin_user, new["id"]) if is_po else api._get_invoice(db_session, admin_user, new["id"])
    context = context_builder(db_session, document, datetime(2026, 10, 27, tzinfo=UTC))
    assert ("Account No.", "000123450000") in context.bank_detail_rows
    assert ("IFSC Code.", "TEST0001234") in context.bank_detail_rows
    assert "000123450000" in build_invoice_html(context)
    assert new["final_total"] == original["final_total"]
    if not is_po:
        assert new["bank_account_id"] == chosen["id"]
        db_session.refresh(document)
        assert document.bank_account_number == "000123450000"
        assert db_session.get(Invoice, original["id"]).bank_account_number == old["account_number"]
    replay = client.post(url + "/generate-pdf", headers=headers)
    assert replay.status_code == 200, replay.text
    assert replay.json()["pdf_sha256"] == final_metadata["pdf_sha256"]
    assert replay.json()["pdf_storage_key"] == final_metadata["pdf_storage_key"]
    assert client.get(url + "/pdf", headers=headers).content == final_bytes
