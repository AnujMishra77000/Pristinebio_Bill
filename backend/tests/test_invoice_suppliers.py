"""Changing pickup suppliers must not change company headers or past bills."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import runpy

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text

from app.models.invoice import Invoice, InvoiceCreationRequest, InvoiceRevision
from app.schemas.invoice import InvoiceCreate
from app.services.invoice_pdf import build_invoice_context
from tests.test_financial_correctness import _address, _invoice_payload


def test_forward_supplier_migration_preserves_issued_invoice_snapshots():
    migration = runpy.run_path(str(Path(__file__).parents[1] / 'alembic/versions/20261004_0021_invoice_pickup_supplier.py'))
    engine = create_engine('sqlite+pysqlite:///:memory:')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE suppliers (id INTEGER PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE invoices (id INTEGER PRIMARY KEY, company_registered_address TEXT, pickup_address TEXT, final_total NUMERIC(14, 2), pdf_storage_key TEXT)'))
        connection.execute(text("INSERT INTO invoices VALUES (1, 'Original Company', 'Original Pickup', 346849.00, 'issued-original.pdf')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration['upgrade']()
        row = connection.execute(text('SELECT * FROM invoices')).mappings().one()
        assert row['supplier_id'] is None
        assert row['company_registered_address'] == 'Original Company'
        assert row['pickup_address'] == 'Original Pickup'
        assert row['final_total'] == 346849
        assert row['pdf_storage_key'] == 'issued-original.pdf'
        schema = inspect(connection)
        assert any(index['name'] == 'ix_invoices_supplier_id' for index in schema.get_indexes('invoices'))
        assert any(fk['name'] == 'fk_invoices_supplier' for fk in schema.get_foreign_keys('invoices'))
    engine.dispose()


def _supplier(client, headers, branch, name, *, default=False):
    response = client.post('/api/v1/suppliers', headers=headers, json={
        'branch_id': branch.id, 'name': name, 'is_default': default,
        'address': _address(name, address_line1=f'{name} Warehouse'),
    })
    assert response.status_code == 201, response.text
    return response.json()


def _payload(client, headers, branch, document_type):
    payload = _invoice_payload(branch)
    payload['document_type'] = document_type
    if document_type == 'reagent':
        manufacturer = client.post('/api/v1/manufacturers', headers=headers,
                                   json={'branch_id': branch.id, 'name': 'Sigma', 'code': 'SIG'}).json()
        payload['lines'][0].update(manufacturer_id=manufacturer['id'], unit='g')
    return payload


@pytest.mark.parametrize('document_type', ['sales', 'reagent'])
def test_explicit_supplier_overrides_default_and_keeps_company_address(
    client, auth_headers, staff_user, branch, company, db_session, document_type,
):
    headers = auth_headers(staff_user)
    _supplier(client, headers, branch, 'Default', default=True)
    chosen = _supplier(client, headers, branch, 'Chosen')
    payload = {**_payload(client, headers, branch, document_type), 'supplier_id': chosen['id']}
    created = client.post('/api/v1/invoices', headers={**headers, 'Idempotency-Key': 'chosen-supplier'}, json=payload)
    assert created.status_code == 201, created.text
    assert created.json()['supplier_id'] == chosen['id']
    assert created.json()['company_registered_address'] == '1 Billing Street'
    assert created.json()['pickup_address'] == 'Chosen Warehouse, Industrial Area, Hyderabad, Telangana - 500001'
    assert client.patch(f"/api/v1/suppliers/{chosen['id']}", headers=headers,
                        json={'address': _address('Changed', address_line1='Changed Warehouse')}).status_code == 200
    replay = client.post('/api/v1/invoices', headers={**headers, 'Idempotency-Key': 'chosen-supplier'}, json=payload)
    assert replay.status_code == 200 and replay.json()['id'] == created.json()['id']
    assert replay.json()['pickup_address'] == 'Chosen Warehouse, Industrial Area, Hyderabad, Telangana - 500001'
    changed_payload = {**payload, 'supplier_id': None}
    assert client.post('/api/v1/invoices', headers={**headers, 'Idempotency-Key': 'chosen-supplier'}, json=changed_payload).status_code == 409
    context = build_invoice_context(db_session.get(Invoice, created.json()['id']), company=company, branch=branch, generated_at=datetime.now(UTC))
    assert context.seller.address_lines == ('1 Billing Street',)
    assert context.seller.pickup_address == 'Chosen Warehouse, Industrial Area, Hyderabad, Telangana - 500001'


@pytest.mark.parametrize('document_type', ['sales', 'reagent'])
def test_supplier_draft_edit_requires_version_preserves_revisions_and_freezes_at_approval(
    client, auth_headers, staff_user, admin_user, branch, db_session, document_type,
):
    headers = auth_headers(staff_user)
    first = _supplier(client, headers, branch, 'First', default=True)
    second = _supplier(client, headers, branch, 'Second')
    payload = {**_payload(client, headers, branch, document_type), 'supplier_id': first['id']}
    created = client.post('/api/v1/invoices', headers=headers, json=payload).json()
    document_id = created['id']
    endpoint = f'/api/v1/invoices/{document_id}'
    assert client.patch(endpoint, headers=headers, json={'supplier_id': second['id']}).status_code == 422
    edited = client.patch(endpoint, headers=headers, json={'supplier_id': second['id'], 'expected_version': 1})
    assert edited.status_code == 200, edited.text
    assert edited.json()['version'] == 2
    assert edited.json()['company_registered_address'] == '1 Billing Street'
    assert edited.json()['pickup_address'] == 'Second Warehouse, Industrial Area, Hyderabad, Telangana - 500001'
    assert client.patch(endpoint, headers=headers, json={'supplier_id': first['id'], 'expected_version': 1}).status_code == 409
    revisions = list(db_session.scalars(select(InvoiceRevision).where(InvoiceRevision.invoice_id == document_id).order_by(InvoiceRevision.id)))
    assert revisions[0].snapshot['seller_addresses']['supplier_id'] == first['id']
    assert revisions[1].snapshot['seller_addresses']['supplier_id'] == second['id']
    historical_delete = client.delete(f"/api/v1/suppliers/{first['id']}", headers=headers)
    assert historical_delete.status_code == 409
    assert 'deactivate' in str(historical_delete.json()['detail']).lower()
    assert client.post(endpoint+'/submit', headers=headers, json={'expected_version': 2}).status_code == 200
    assert client.patch(f"/api/v1/suppliers/{second['id']}", headers=headers,
                        json={'address': _address('Changed', address_line1='Changed Master')}).status_code == 200
    approved = client.post(endpoint+'/approve', headers=auth_headers(admin_user), json={'expected_version': 2})
    assert approved.status_code == 200, approved.text
    assert approved.json()['supplier_id'] == second['id']
    assert approved.json()['pickup_address'] == 'Second Warehouse, Industrial Area, Hyderabad, Telangana - 500001'
    assert client.patch(endpoint, headers=headers, json={'supplier_id': first['id'], 'expected_version': 2}).status_code == 409
    deleted = client.delete(f"/api/v1/suppliers/{second['id']}", headers=headers)
    assert deleted.status_code == 409 and 'deactivate' in str(deleted.json()['detail']).lower()
    assert client.patch(f"/api/v1/suppliers/{second['id']}", headers=headers, json={'is_active': False}).status_code == 200
    assert client.get(endpoint, headers=headers).json()['pickup_address'] == 'Second Warehouse, Industrial Area, Hyderabad, Telangana - 500001'


@pytest.mark.parametrize('document_type', ['sales', 'reagent'])
def test_same_supplier_edit_preserves_saved_pickup(client, auth_headers, staff_user, branch, document_type):
    headers = auth_headers(staff_user)
    supplier = _supplier(client, headers, branch, 'Original')
    payload = {**_payload(client, headers, branch, document_type), 'supplier_id': supplier['id']}
    invoice = client.post('/api/v1/invoices', headers=headers, json=payload).json()
    client.patch(f"/api/v1/suppliers/{supplier['id']}", headers=headers,
                 json={'address': _address('Changed', address_line1='Changed Warehouse'), 'is_active': False})
    edited = client.patch(f"/api/v1/invoices/{invoice['id']}", headers=headers,
                          json={'supplier_id': supplier['id'], 'payment_terms': '60 days', 'expected_version': invoice['version']})
    assert edited.status_code == 200, edited.text
    assert edited.json()['pickup_address'] == invoice['pickup_address']
    assert edited.json()['company_registered_address'] == invoice['company_registered_address']
    assert edited.json()['payment_terms'] == '60 days'


@pytest.mark.parametrize('invalid', ['inactive', 'foreign', 'missing', 'zero', 'fraction', 'boolean'])
def test_preview_and_save_reject_invalid_supplier_without_writes(
    client, auth_headers, staff_user, admin_user, branch, other_branch, db_session, invalid,
):
    headers = auth_headers(staff_user)
    if invalid in ('inactive', 'foreign'):
        supplier = _supplier(client, auth_headers(admin_user), other_branch if invalid == 'foreign' else branch, 'Blocked')
        supplier_id = supplier['id']
        if invalid == 'inactive':
            client.patch(f'/api/v1/suppliers/{supplier_id}', headers=headers, json={'is_active': False})
    else:
        supplier_id = {'missing': 999999, 'zero': 0, 'fraction': 1.5, 'boolean': True}[invalid]
    payload = {**_invoice_payload(branch), 'supplier_id': supplier_id}
    for path in ('/api/v1/invoices/preview', '/api/v1/invoices'):
        response = client.post(path, headers=headers, json=payload)
        assert response.status_code == 422, response.text
        assert 'supplier' in str(response.json()['detail']).lower()
    assert list(db_session.scalars(select(Invoice))) == []


def test_omitted_supplier_retains_default_compatibility_explicit_null_clears(
    client, auth_headers, staff_user, branch,
):
    headers = auth_headers(staff_user)
    default = _supplier(client, headers, branch, 'Default', default=True)
    created = client.post('/api/v1/invoices', headers=headers, json=_invoice_payload(branch))
    assert created.status_code == 201, created.text
    assert created.json()['supplier_id'] == default['id']
    null_create = client.post('/api/v1/invoices', headers=headers, json={**_invoice_payload(branch), 'supplier_id': None})
    assert null_create.status_code == 201, null_create.text
    assert null_create.json()['supplier_id'] is None and null_create.json()['pickup_address'] == ''
    endpoint = f"/api/v1/invoices/{created.json()['id']}"
    unchanged = client.patch(endpoint, headers=headers, json={'expected_version': 1, 'payment_terms': '20 days'})
    assert unchanged.json()['supplier_id'] == default['id']
    cleared = client.patch(endpoint, headers=headers, json={'expected_version': 2, 'supplier_id': None})
    assert cleared.status_code == 200
    assert cleared.json()['supplier_id'] is None and cleared.json()['pickup_address'] == ''


def test_search_is_scoped_active_bounded_and_treats_wildcards_as_text(
    client, auth_headers, staff_user, admin_user, branch, other_branch,
):
    headers = auth_headers(staff_user)
    first = _supplier(client, headers, branch, 'Alpine Chemical')
    second = _supplier(client, headers, branch, 'Alpine Reagents')
    _supplier(client, auth_headers(admin_user), other_branch, 'Alpine Other Profile')
    inactive = _supplier(client, headers, branch, 'Alpine Inactive')
    client.patch(f"/api/v1/suppliers/{inactive['id']}", headers=headers, json={'is_active': False})
    found = client.get(f'/api/v1/suppliers?search=  ALPINE &active_only=true&branch_id={branch.id}', headers=headers)
    assert [record['id'] for record in found.json()] == [first['id'], second['id']]
    assert len(client.get('/api/v1/suppliers?active_only=true&search=Alpine&limit=1', headers=headers).json()) == 1
    assert client.get('/api/v1/suppliers?search=%25&active_only=true', headers=headers).json() == []
    assert client.get(f'/api/v1/suppliers?branch_id={other_branch.id}&search=Alpine', headers=headers).status_code == 403


def test_legacy_idempotency_payload_hash_still_replays_without_supplier_field(
    client, auth_headers, staff_user, branch, db_session,
):
    headers = {**auth_headers(staff_user), 'Idempotency-Key': 'legacy-supplier-omitted'}
    payload = _invoice_payload(branch)
    created = client.post('/api/v1/invoices', headers=headers, json=payload)
    assert created.status_code == 201, created.text
    request = db_session.scalar(select(InvoiceCreationRequest).where(InvoiceCreationRequest.idempotency_key == 'legacy-supplier-omitted'))
    legacy_payload = InvoiceCreate.model_validate(payload).model_dump(mode='json', exclude={'supplier_id'})
    # The historical payload predates Pack/Size as well as supplier selection.
    for line in legacy_payload['lines']:
        line.pop('pack_size', None)
    request.payload_hash = hashlib.sha256(json.dumps(legacy_payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    db_session.commit()
    replay = client.post('/api/v1/invoices', headers=headers, json=payload)
    assert replay.status_code == 200 and replay.json()['id'] == created.json()['id']
