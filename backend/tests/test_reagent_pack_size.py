"""Pack sizes are descriptive transaction snapshots, not quantity multipliers."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from playwright.sync_api import sync_playwright
from sqlalchemy import create_engine, inspect, select, text

from app.models.invoice import Invoice, InvoiceCreationRequest, InvoiceRevision
from app.models.purchase_order import PurchaseOrder, PurchaseOrderCreationRequest, PurchaseOrderRevision
from app.schemas.invoice import InvoiceCreate
from app.schemas.purchase_order import PurchaseOrderCreate
from app.services.invoice_pdf import build_invoice_context, build_reagent_purchase_order_context, build_invoice_html, render_invoice_pdf
from tests.test_financial_correctness import _address, _invoice_payload, _purchase_order_payload


def _request(client, headers, branch, kind):
    manufacturer = client.post('/api/v1/manufacturers', headers=headers, json={
        'branch_id': branch.id, 'name': 'Sigma', 'code': 'SIG', 'is_active': True,
    })
    assert manufacturer.status_code == 201, manufacturer.text
    if kind == 'bill':
        endpoint, model, revision_model = '/api/v1/invoices', Invoice, InvoiceRevision
        payload = _invoice_payload(branch)
    else:
        endpoint, model, revision_model = '/api/v1/purchase-orders', PurchaseOrder, PurchaseOrderRevision
        payload = _purchase_order_payload(branch)
        payload.update(place_of_supply_state_code='36', purchaser={'name': 'Research Purchaser', 'address': _address('Lab')})
    payload['document_type'] = 'reagent'
    payload['lines'][0].update(manufacturer_id=manufacturer.json()['id'], unit='g', part_no='SIG-100', pack_size=' 500 g ')
    return endpoint, model, revision_model, payload


@pytest.mark.parametrize('kind', ['bill', 'po'])
def test_pack_size_survives_preview_edits_approval_and_revision_snapshots(client, auth_headers, staff_user, manager_user, branch, company, db_session, kind):
    headers = auth_headers(staff_user)
    endpoint, model, revision_model, payload = _request(client, headers, branch, kind)
    preview = client.post(f'{endpoint}/preview', headers=headers, json=payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()['lines'][0].get('pack_size') == '500 g'
    created = client.post(endpoint, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    document = created.json()
    document_id = document['id']
    assert document['lines'][0]['pack_size'] == '500 g'
    assert document['final_total'] == preview.json()['final_total'] == '118.00'

    changed_lines = [{**payload['lines'][0], 'pack_size': '10 × 2 mL'}]
    changes = {'lines': changed_lines} if kind == 'bill' else {'reagent_details': {**payload, 'lines': changed_lines}}
    edited = client.patch(f'{endpoint}/{document_id}', headers=headers, json={'expected_version': 1, **changes})
    assert edited.status_code == 200, edited.text
    assert edited.json()['lines'][0]['pack_size'] == '10 × 2 mL'
    assert edited.json()['final_total'] == '118.00'
    assert client.post(f'{endpoint}/{document_id}/submit', headers=headers, json={'expected_version': 2}).status_code == 200
    approved = client.post(f'{endpoint}/{document_id}/approve', headers=auth_headers(manager_user), json={'expected_version': 2})
    assert approved.status_code == 200, approved.text
    assert approved.json()['lines'][0]['pack_size'] == '10 × 2 mL'
    assert approved.json()['final_total'] == '118.00'
    assert client.patch(f'{endpoint}/{document_id}', headers=headers, json={'expected_version': 2, **changes}).status_code == 409
    foreign_key = revision_model.invoice_id if kind == 'bill' else revision_model.purchase_order_id
    revisions = list(db_session.scalars(select(revision_model).where(foreign_key == document_id).order_by(revision_model.id)))
    assert revisions[0].snapshot['lines'][0]['pack_size'] == '500 g'
    assert any(revision.snapshot['lines'][0]['pack_size'] == '10 × 2 mL' for revision in revisions[1:])
    stored = db_session.get(model, document_id)
    builder = build_invoice_context if kind == 'bill' else build_reagent_purchase_order_context
    context = builder(stored, company=company, branch=branch, generated_at=datetime.now(UTC))
    assert context.lines[0].pack_size == '10 × 2 mL'


@pytest.mark.parametrize('kind', ['bill', 'po'])
def test_pack_size_is_part_of_save_idempotency_but_blank_values_preserve_old_hashes(client, auth_headers, staff_user, branch, db_session, kind):
    headers = {**auth_headers(staff_user), 'Idempotency-Key': 'pack-size-save'}
    endpoint, model, _, payload = _request(client, headers, branch, kind)
    created = client.post(endpoint, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    replay = client.post(endpoint, headers=headers, json=payload)
    assert replay.status_code == 200 and replay.json()['id'] == created.json()['id']
    changed = {**payload, 'lines': [{**payload['lines'][0], 'pack_size': '100 mL'}]}
    assert client.post(endpoint, headers=headers, json=changed).status_code == 409
    assert db_session.get(model, created.json()['id']).lines[0].pack_size == '500 g'

    old_payload = {**payload, 'lines': [{key: value for key, value in payload['lines'][0].items() if key != 'pack_size'}]}
    if kind == 'bill':
        old_payload['invoice_number_suffix'] = 'LEGACY-PACK'
    old_headers = {**headers, 'Idempotency-Key': 'before-pack-size-field'}
    old_created = client.post(endpoint, headers=old_headers, json=old_payload)
    assert old_created.status_code == 201, old_created.text
    schema = InvoiceCreate if kind == 'bill' else PurchaseOrderCreate
    old_json = schema.model_validate(old_payload).model_dump(mode='json', exclude={'lines': {'__all__': {'pack_size'}}})
    old_json.pop('supplier_id' if kind == 'bill' else 'purchase_order_number', None)
    old_hash = hashlib.sha256(json.dumps(old_json, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    request_model = InvoiceCreationRequest if kind == 'bill' else PurchaseOrderCreationRequest
    saved_request = db_session.scalar(select(request_model).where(request_model.idempotency_key == 'before-pack-size-field'))
    saved_request.payload_hash = old_hash
    db_session.commit()
    for pack_value in (None, '   '):
        replay_payload = {**old_payload, 'lines': [{**old_payload['lines'][0], 'pack_size': pack_value}]}
        replay = client.post(endpoint, headers=old_headers, json=replay_payload)
        assert replay.status_code == 200, replay.text
        assert replay.json()['id'] == old_created.json()['id']
        assert replay.json()['lines'][0]['pack_size'] is None


@pytest.mark.parametrize('kind', ['bill', 'po'])
@pytest.mark.parametrize('value', ['x' * 101, 100, '500 g\x00'])
def test_invalid_pack_sizes_return_line_field_errors(client, auth_headers, staff_user, branch, kind, value):
    headers = auth_headers(staff_user)
    endpoint, _, _, payload = _request(client, headers, branch, kind)
    payload['lines'][0]['pack_size'] = value
    response = client.post(endpoint, headers=headers, json=payload)
    assert response.status_code == 422, response.text
    assert any(error['loc'] == ['body', 'lines', 0, 'pack_size'] for error in response.json()['detail'])


def test_pack_size_migration_preserves_existing_line_data_and_issued_pdf_references(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path / "migration.sqlite"}')
    with engine.begin() as connection:
        for table in ('invoice_lines', 'purchase_order_lines'):
            connection.execute(text(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, product_name TEXT, quantity NUMERIC, line_total NUMERIC)'))
            connection.execute(text(f"INSERT INTO {table} VALUES (1, 'Historical product', 2, 118)"))
        connection.execute(text('CREATE TABLE invoices (id INTEGER PRIMARY KEY, pdf_storage_key TEXT, pdf_sha256 TEXT)'))
        connection.execute(text("INSERT INTO invoices VALUES (1, 'issued.pdf', 'original-checksum')"))
        migration = runpy.run_path(str(Path(__file__).parents[1] / 'alembic/versions/20261005_0022_reagent_pack_size.py'))
        with Operations.context(MigrationContext.configure(connection)):
            migration['upgrade']()
        for table in ('invoice_lines', 'purchase_order_lines'):
            assert 'pack_size' in {column['name'] for column in inspect(connection).get_columns(table)}
            assert tuple(connection.execute(text(f'SELECT product_name, quantity, line_total, pack_size FROM {table}')).one()) == ('Historical product', 2, 118, None)
        assert tuple(connection.execute(text('SELECT pdf_storage_key, pdf_sha256 FROM invoices')).one()) == ('issued.pdf', 'original-checksum')


@pytest.mark.parametrize('kind', ['bill', 'po'])
@pytest.mark.parametrize('item_count', [1, 20])
def test_reagent_pack_size_pdf_column_wraps_and_renders_all_copies(client, auth_headers, staff_user, branch, company, db_session, tmp_path, kind, item_count):
    headers = auth_headers(staff_user)
    endpoint, model, _, payload = _request(client, headers, branch, kind)
    long_pack = '10 × 2 mL / individually sealed laboratory reference ampoules'
    payload['lines'] = [{**payload['lines'][0], 'pack_size': '500 g' if index % 2 == 0 else long_pack} for index in range(item_count)]
    created = client.post(endpoint, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    builder = build_invoice_context if kind == 'bill' else build_reagent_purchase_order_context
    context = builder(db_session.get(model, created.json()['id']), company=company, branch=branch, generated_at=datetime.now(UTC))
    html = build_invoice_html(context)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.emulate_media(media='print')
            page.set_content(html, wait_until='load')
            headings = page.locator('.item-heading').first.locator('th').all_inner_texts()
            assert headings == ['Sr. No.', 'Item Description', 'HSN/SAC', 'GST', 'Quantity', 'Pack/Size', 'Rate', 'Disc %', 'Amount']
            cells = page.locator('.item-pack-size')
            assert cells.count() == item_count * 4
            assert cells.all_inner_texts().count('500 g') == ((item_count + 1) // 2) * 4
            assert all(cells.evaluate_all('nodes => nodes.map(node => node.scrollWidth <= node.clientWidth + 1)'))
        finally:
            browser.close()
    output = tmp_path / f'reagent-{kind}-pack-size-{item_count}.pdf'
    output.write_bytes(render_invoice_pdf(context).pdf_bytes)
    info = subprocess.run(['pdfinfo', str(output)], capture_output=True, text=True, check=True).stdout
    pages = next(int(line.split(':', 1)[1]) for line in info.splitlines() if line.startswith('Pages:'))
    assert '(A4)' in info and pages % 4 == 0
    if item_count == 1:
        assert pages == 4
    subprocess.run(['pdftoppm', '-scale-to', '1400', '-png', str(output), str(output.with_suffix(''))], check=True, capture_output=True)
    assert len(list(tmp_path.glob('*.png'))) == pages
