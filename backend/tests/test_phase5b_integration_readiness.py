from app.models.enums import InvoiceStatus
from app.models.integration import IntegrationAuditLog, IntegrationReconciliation, OutboundIntegrationJob
from app.models.invoice import Invoice
from app.schemas.integration import ProviderResponse
from tests.test_phase5a_payments import _approved_invoice


def _job_payload(invoice_id: int, branch_id: int, claimed_external_reference: str | None = None) -> dict:
    payload = {
        "invoice_id": invoice_id,
        "branch_id": branch_id,
        "provider_key": "client-accounting",
        "operation": "invoice_submission",
    }
    if claimed_external_reference is not None:
        payload["claimed_external_reference"] = claimed_external_reference
    return payload


def test_unconfigured_provider_is_persisted_without_fake_external_success(client, auth_headers, staff_user, manager_user, branch, db_session):
    _, invoice = _approved_invoice(client, auth_headers, staff_user, manager_user, branch)
    response = client.post(
        "/api/v1/integrations/jobs",
        headers={**auth_headers(manager_user), "Idempotency-Key": "integration-1"},
        json=_job_payload(invoice["id"], branch.id, "user-entered-irn"),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["external_reference"] is None
    assert body["external_status"] is None
    assert db_session.get(Invoice, invoice["id"]).status == InvoiceStatus.APPROVED
    assert db_session.query(IntegrationReconciliation).filter_by(job_id=body["id"], status="open").count() == 1


def test_integration_creation_replays_same_payload_and_conflicts_on_changed_payload(client, auth_headers, staff_user, manager_user, branch):
    _, invoice = _approved_invoice(client, auth_headers, staff_user, manager_user, branch)
    headers = {**auth_headers(manager_user), "Idempotency-Key": "integration-same"}
    payload = _job_payload(invoice["id"], branch.id)
    first = client.post("/api/v1/integrations/jobs", headers=headers, json=payload)
    replay = client.post("/api/v1/integrations/jobs", headers=headers, json=payload)
    conflict = client.post("/api/v1/integrations/jobs", headers=headers, json={**payload, "claimed_external_reference": "different"})
    assert first.status_code == replay.status_code == 201
    assert replay.headers["X-Idempotent-Replay"] == "true"
    assert first.json()["id"] == replay.json()["id"]
    assert conflict.status_code == 409


def test_staff_cannot_create_or_list_integration_jobs(client, auth_headers, staff_user, manager_user, branch):
    _, invoice = _approved_invoice(client, auth_headers, staff_user, manager_user, branch)
    create = client.post(
        "/api/v1/integrations/jobs",
        headers={**auth_headers(staff_user), "Idempotency-Key": "staff-integration"},
        json=_job_payload(invoice["id"], branch.id),
    )
    listed = client.get("/api/v1/integrations/jobs", headers=auth_headers(staff_user))
    assert create.status_code == 403
    assert listed.status_code == 403


def test_only_approved_invoices_can_create_integration_jobs(client, auth_headers, staff_user, manager_user, branch):
    from tests.test_invoices import _create_customer, _create_product, _create_invoice

    customer = _create_customer(client, auth_headers, staff_user, branch, name="Unapproved Customer")
    product = _create_product(client, auth_headers, staff_user, branch, name="Unapproved Product")
    invoice = _create_invoice(client, auth_headers, staff_user, branch, customer["id"], product["id"])
    response = client.post(
        "/api/v1/integrations/jobs",
        headers={**auth_headers(manager_user), "Idempotency-Key": "unapproved-integration"},
        json=_job_payload(invoice["id"], branch.id),
    )
    assert response.status_code == 422


def test_retry_is_bounded_and_audited(client, auth_headers, staff_user, manager_user, branch, db_session):
    _, invoice = _approved_invoice(client, auth_headers, staff_user, manager_user, branch)
    created = client.post(
        "/api/v1/integrations/jobs",
        headers={**auth_headers(manager_user), "Idempotency-Key": "integration-retry"},
        json=_job_payload(invoice["id"], branch.id),
    )
    job_id = created.json()["id"]
    for expected_attempt in (1, 2, 3):
        retried = client.post(f"/api/v1/integrations/jobs/{job_id}/retry", headers=auth_headers(manager_user))
        assert retried.status_code == 200
        assert retried.json()["status"] == "unavailable"
        assert retried.json()["attempt_count"] == expected_attempt
    exhausted = client.post(f"/api/v1/integrations/jobs/{job_id}/retry", headers=auth_headers(manager_user))
    assert exhausted.status_code == 200
    assert exhausted.json()["status"] == "failed"
    assert exhausted.json()["last_error_code"] == "retry_exhausted"
    assert db_session.query(IntegrationAuditLog).filter_by(job_id=job_id).count() == 5


def test_reconciliation_and_numbering_review_are_authorized_and_truthful(client, auth_headers, staff_user, manager_user):
    providers = client.get("/api/v1/integrations/providers", headers=auth_headers(manager_user))
    numbering = client.get("/api/v1/integrations/numbering-review", headers=auth_headers(manager_user))
    assert providers.status_code == 200
    assert providers.json()[0]["available"] is False
    assert "credentials" in providers.json()[0]["reason"]
    assert numbering.status_code == 200
    assert numbering.json()["current_series"] == "PBPL/{financial_year}/{staff_entered_suffix}"
    assert "cross-type duplicates" in numbering.json()["compatibility"]
    assert numbering.json()["proposed_series"] == "No numbering change proposed"
    assert "issued" in numbering.json()["migration_policy"]
    assert client.get("/api/v1/integrations/providers", headers=auth_headers(staff_user)).status_code == 403


def test_provider_response_contract_requires_authoritative_acceptance_fields():
    import pytest

    with pytest.raises(ValueError):
        ProviderResponse(status="accepted")
    response = ProviderResponse(status="uncertain")
    assert response.status == "uncertain"
