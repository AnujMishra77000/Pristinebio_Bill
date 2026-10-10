from datetime import UTC, date, datetime
from decimal import Decimal
import subprocess
from pathlib import Path
import runpy

import pytest
from playwright.sync_api import sync_playwright
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text

from app.models.invoice import Invoice
from app.models.purchase_order import PurchaseOrder
from app.services.invoice_pdf import (
    build_invoice_context, build_purchase_order_context,
    build_reagent_purchase_order_context, build_invoice_html, render_invoice_pdf,
)
from tests.test_financial_correctness import _invoice_payload, _purchase_order_payload, _address


def test_domestic_po_dispatch_is_saved_edited_and_preserved_on_approval(
    client, auth_headers, admin_user, company, branch, db_session
):
    payload = {**_purchase_order_payload(branch), "transport_mode": "  ROAD / Courier  "}
    headers = {**auth_headers(admin_user), "Idempotency-Key": "domestic-dispatch-save"}
    created = client.post("/api/v1/purchase-orders", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["transport_mode"] == "ROAD / Courier"
    replay = client.post("/api/v1/purchase-orders", headers=headers, json=payload)
    assert replay.status_code == 200 and replay.json()["id"] == created.json()["id"]
    document = db_session.get(PurchaseOrder, created.json()["id"])
    context = build_purchase_order_context(document, company=company, branch=branch,
                                           generated_at=datetime(2026, 10, 8, 12, tzinfo=UTC))
    assert context.transport_mode == "ROAD / Courier"
    assert "ROAD / Courier" in build_invoice_html(context)

    url = f"/api/v1/purchase-orders/{document.id}"
    edited = client.patch(url, headers=auth_headers(admin_user), json={
        "expected_version": document.version,
        "domestic_details": {**payload, "transport_mode": "  RAIL  "},
    })
    assert edited.status_code == 200, edited.text
    assert edited.json()["transport_mode"] == "RAIL"
    assert edited.json()["final_total"] == created.json()["final_total"]
    stale = client.patch(url, headers=auth_headers(admin_user), json={
        "expected_version": created.json()["version"], "domestic_details": payload,
    })
    assert stale.status_code == 409
    submitted = client.post(url + "/submit", headers=auth_headers(admin_user),
                            json={"expected_version": edited.json()["version"]})
    assert submitted.status_code == 200, submitted.text
    approved = client.post(url + "/approve", headers=auth_headers(admin_user),
                           json={"expected_version": submitted.json()["version"]})
    assert approved.status_code == 200, approved.text
    db_session.refresh(document)
    final = build_purchase_order_context(document, company=company, branch=branch, generated_at=context.generated_at)
    assert final.transport_mode == "RAIL"
    assert "RAIL" in build_invoice_html(final)
    assert final.final_total == context.final_total
    locked = client.patch(url, headers=auth_headers(admin_user), json={
        "expected_version": approved.json()["version"],
        "domestic_details": {**payload, "transport_mode": "AIR"},
    })
    assert locked.status_code == 409
    db_session.refresh(document)
    assert document.transport_mode == "RAIL"


@pytest.mark.parametrize("value", [None, "   "])
def test_domestic_po_dispatch_can_be_cleared_but_an_omitted_edit_preserves_it(
    client, auth_headers, admin_user, branch, value, db_session
):
    payload = _purchase_order_payload(branch)
    created = client.post("/api/v1/purchase-orders", headers=auth_headers(admin_user),
                          json={**payload, "transport_mode": "ROAD"})
    assert created.status_code == 201, created.text
    assert created.json()["transport_mode"] == "ROAD"
    url = f"/api/v1/purchase-orders/{created.json()['id']}"
    omitted = client.patch(url, headers=auth_headers(admin_user), json={
        "expected_version": created.json()["version"], "domestic_details": payload,
    })
    assert omitted.status_code == 200, omitted.text
    assert omitted.json()["transport_mode"] == "ROAD"
    cleared = client.patch(url, headers=auth_headers(admin_user), json={
        "expected_version": omitted.json()["version"],
        "domestic_details": {**payload, "transport_mode": value},
    })
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["transport_mode"] is None
    assert db_session.get(PurchaseOrder, created.json()["id"]).transport_mode is None


def test_domestic_po_dispatch_rejects_excess_length_without_saving_changes(
    client, auth_headers, admin_user, branch
):
    payload = _purchase_order_payload(branch)
    invalid = client.post("/api/v1/purchase-orders", headers=auth_headers(admin_user),
                          json={**payload, "transport_mode": "X" * 101})
    assert invalid.status_code == 422
    assert invalid.json()["detail"][0]["loc"][-1] == "transport_mode"


@pytest.fixture
def bill_context_factory(client, auth_headers, admin_user, branch, company, db_session):
    branch.email = "billing@example.com"
    branch.secondary_email = "orders@example.com"
    branch.phone = "9000000000"
    branch.bank_account_name = "Example Chemicals"
    branch.bank_account_number = "TEST123456"
    branch.bank_ifsc_code = "TEST0000001"
    db_session.commit()

    def create(kind, interstate=False, line_count=1, gst_rates=None):
        is_po = kind in {"purchase", "reagent_purchase"}
        is_reagent = kind in {"reagent", "reagent_purchase"}
        payload = _purchase_order_payload(branch) if is_po else _invoice_payload(branch)
        payload.update(vehicle_number="TS09AB1234", payment_terms="30 Days")
        if is_po:
            payload["purchaser"] = {"name": "Delivery Company", "address": _address("Delivery Company"), "is_active": True}
        else:
            payload["consignee"] = {"name": "Delivery Company", "billing_address": _address("Delivery Company"), "is_active": True}
        if is_reagent:
            manufacturer = client.post("/api/v1/manufacturers", headers=auth_headers(admin_user), json={
                "branch_id": branch.id, "code": "SIG", "name": "Sigma", "is_active": True,
            }).json()
            payload["document_type"] = "reagent"
            payload["place_of_supply_state_code"] = "36"
            payload["lines"][0].update(manufacturer_id=manufacturer["id"], part_no="ART-001", unit="GM", pack_size="500 g", discount_percent="10.00")
        if interstate:
            payload["place_of_supply_state_code"] = "29"
            if is_po and not is_reagent:
                payload["supplier"]["address"]["state_code"] = "29"
                payload["supplier"]["gstin"] = "29FGHIJ1234K1Z5"
        payload["lines"] = [{**payload["lines"][0], "product_name": f"Reference material {i + 1}"} for i in range(line_count)]
        if gst_rates:
            for line, rate in zip(payload["lines"], gst_rates, strict=True):
                line["gst_rate"] = rate
        route = "/api/v1/purchase-orders" if is_po else "/api/v1/invoices"
        response = client.post(route, headers=auth_headers(admin_user), json=payload)
        assert response.status_code == 201, response.text
        document = db_session.get(PurchaseOrder if is_po else Invoice, response.json()["id"])
        builder = build_reagent_purchase_order_context if kind == "reagent_purchase" else build_purchase_order_context if is_po else build_invoice_context
        context = builder(document, company=company, branch=branch, generated_at=datetime(2026, 10, 7, 12, tzinfo=UTC))
        return document, context, builder, route
    return create


@pytest.mark.parametrize("expected_date", ["2026-10-09", None])
def test_domestic_po_delivery_date_is_saved_and_shown_only_in_invoice_details(
    bill_context_factory, client, auth_headers, admin_user, company, branch, db_session, expected_date
):
    document, before, builder, route = bill_context_factory("purchase")
    response = client.patch(
        f"{route}/{document.id}", headers=auth_headers(admin_user),
        json={"expected_version": document.version, "expected_delivery_date": expected_date},
    )
    assert response.status_code == 200, response.text
    assert response.json()["expected_delivery_date"] == expected_date
    db_session.refresh(document)
    context = builder(document, company=company, branch=branch, generated_at=before.generated_at)
    assert context.expected_delivery_date == (date(2026, 10, 9) if expected_date else None)
    assert context.final_total == before.final_total
    html = build_invoice_html(context)
    identity, parties = html.split('<div class="party-grid">', 1)
    parties = parties.split('<table class="items-table', 1)[0]
    assert "Delivery Note Date:" not in html
    assert "Expected Delivery Date:" not in parties
    assert context.consignee.shipment_lines == ()
    assert ("Expected Delivery Date:" in identity) == bool(expected_date)
    if expected_date:
        assert "09-Oct-2026" in identity
        assert "09-Oct-2026" not in parties
        assert html.count("Expected Delivery Date:") == len(context.copy_labels)


@pytest.mark.parametrize("kind", ["sales", "reagent", "reagent_purchase"])
def test_other_bill_delivery_date_placement_is_unchanged(bill_context_factory, company, branch, kind):
    document, before, builder, _ = bill_context_factory(kind)
    document.delivery_note_date = date(2026, 10, 4)
    document.expected_delivery_date = date(2026, 10, 9)
    context = builder(document, company=company, branch=branch, generated_at=before.generated_at)
    html = build_invoice_html(context)
    identity, parties = html.split('<div class="party-grid">', 1)
    parties = parties.split('<table class="items-table', 1)[0]
    assert "Delivery Note Date:" in identity and "04-Oct-2026" in identity
    assert "Expected Delivery Date:" not in identity
    assert "Expected Delivery Date: 09-Oct-2026" in parties
    assert html.count("Expected Delivery Date:") == len(context.copy_labels)


@pytest.mark.parametrize("line_count", [1, 5])
def test_domestic_po_delivery_date_renders_in_identity_without_clipping(
    bill_context_factory, client, auth_headers, admin_user, company, branch, db_session, line_count, tmp_path
):
    document, before, builder, route = bill_context_factory("purchase", line_count=line_count)
    details = _purchase_order_payload(branch)
    details.update(expected_delivery_date="2026-10-09", transport_mode="ROAD / Courier")
    details["lines"] = [
        {**details["lines"][0], "product_name": f"Reference material {index + 1}"}
        for index in range(line_count)
    ]
    response = client.patch(
        f"{route}/{document.id}", headers=auth_headers(admin_user),
        json={"expected_version": document.version, "domestic_details": details},
    )
    assert response.status_code == 200, response.text
    db_session.refresh(document)
    context = builder(document, company=company, branch=branch, generated_at=before.generated_at)
    html = build_invoice_html(context)
    page_count = 1 if line_count == 1 else 2
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.emulate_media(media="print")
            page.set_content(html, wait_until="load")
            sheets = page.locator(".invoice-copy")
            assert sheets.count() == page_count
            for sheet in sheets.all():
                meta = sheet.locator(".invoice-meta")
                assert "Delivery Note Date:" not in meta.inner_text()
                row = meta.locator(".meta-row").filter(has_text="Expected Delivery Date:")
                assert row.count() == 1
                assert row.locator(".meta-label").inner_text() == "Expected Delivery Date:"
                assert row.locator(".meta-value").inner_text() == "09-Oct-2026"
                dispatch = meta.locator(".meta-row").filter(has_text="Dispatched through:")
                assert dispatch.count() == 1
                assert dispatch.locator(".meta-value").inner_text() == "ROAD / Courier"
                assert "Expected Delivery Date:" not in sheet.locator(".party-grid").inner_text()
                assert "09-Oct-2026" not in sheet.locator(".party-grid").inner_text()
                assert row.evaluate("""row => [...row.children].every(child => {
                    const box = child.getBoundingClientRect(), parent = row.getBoundingClientRect();
                    return child.scrollWidth <= child.clientWidth + 1
                        && box.top >= parent.top - 1 && box.bottom <= parent.bottom + 1;
                })""")
        finally:
            browser.close()
    result = render_invoice_pdf(context)
    output = tmp_path / f"purchase-delivery-details-{line_count}.pdf"
    output.write_bytes(result.pdf_bytes)
    metadata = subprocess.run(["pdfinfo", str(output)], check=True, capture_output=True, text=True).stdout
    pages = int(next(line.split(":", 1)[1] for line in metadata.splitlines() if line.startswith("Pages:")))
    assert pages == page_count
    subprocess.run(["pdftoppm", "-png", "-scale-to", "1100", str(output), str(output.with_suffix(""))],
                   check=True, capture_output=True)


@pytest.mark.parametrize("party", ["buyer", "consignee"])
@pytest.mark.parametrize("phone,email", [
    ("9876543210", "party@example.com"),
    ("9876543210", None),
    (None, "party@example.com"),
    (None, None),
])
def test_sales_party_contact_and_email_render_as_independent_optional_rows(
    bill_context_factory, company, branch, party, phone, email
):
    document, before, builder, _ = bill_context_factory("sales")
    setattr(document, f"{party}_phone", phone)
    setattr(document, f"{party}_email", email)
    context = builder(document, company=company, branch=branch, generated_at=before.generated_at)
    displayed_party = getattr(context, party)
    assert displayed_party.contact == phone
    assert displayed_party.email == email

    html = build_invoice_html(context)
    parties = html.split('<div class="party-grid">', 1)[1].split('<table class="items-table', 1)[0]
    panel = parties.split('<div class="party-panel">')[1 if party == "buyer" else 2]
    assert ('class="party-line party-contact"' in panel) == bool(phone)
    assert ('class="party-line party-email"' in panel) == bool(email)
    if phone:
        assert f'<span class="meta-label">Contact:</span> {phone}</p>' in panel
    if email:
        assert f'<span class="meta-label">Email:</span> {email}</p>' in panel
    assert " | " not in panel


def test_sales_vehicle_and_lr_only_appear_in_invoice_details(
    bill_context_factory, company, branch
):
    document, before, builder, _ = bill_context_factory("sales")
    document.vehicle_number = "MH 05 XL1995"
    document.lr_number = "4132"
    document.transport_mode = "ROAD"
    document.vehicle_type = "Truck"
    context = builder(document, company=company, branch=branch, generated_at=before.generated_at)
    html = build_invoice_html(context)
    first_copy = html.split('<div class="party-grid">', 1)
    identity = first_copy[0]
    parties = first_copy[1].split('<table class="items-table', 1)[0]
    assert "Vehicle No.:" in identity and "MH 05 XL1995" in identity
    assert "LR No.:" in identity and "4132" in identity
    assert "MH 05 XL1995" not in parties
    assert "4132" not in parties
    assert context.consignee.shipment_lines == ("Mode of Shipment: ROAD", "Vehicle Type: Truck")
    assert html.count("MH 05 XL1995") == len(context.copy_labels)
    assert html.count("4132") == len(context.copy_labels)


@pytest.mark.parametrize("kind", ["reagent", "purchase", "reagent_purchase"])
def test_other_bill_party_and_transport_presentation_is_unchanged(
    bill_context_factory, company, branch, kind
):
    document, before, builder, _ = bill_context_factory(kind)
    document.lr_number = "4132"
    if kind == "reagent":
        document.buyer_phone = "9876543210"
        document.buyer_email = "buyer@example.com"
        document.consignee_phone = "9000000001"
        document.consignee_email = "shipping@example.com"
    else:
        document.supplier_phone = "9876543210"
        document.supplier_email = "supplier@example.com"
    context = builder(document, company=company, branch=branch, generated_at=before.generated_at)
    if kind == "reagent":
        assert context.buyer.contact == "9876543210 | buyer@example.com"
        assert context.consignee.contact == "9000000001 | shipping@example.com"
        assert context.buyer.email is None and context.consignee.email is None
        assert "LR/Docket No.: 4132" in context.consignee.shipment_lines
    else:
        assert context.buyer.contact == context.consignee.contact == "9876543210"
        assert context.buyer.email == context.consignee.email == "supplier@example.com"
        if kind == "reagent_purchase":
            assert "LR No.: 4132" in context.consignee.shipment_lines


@pytest.mark.parametrize("line_count", [1, 5])
def test_sales_party_details_render_without_duplicate_transport_or_overlap(
    bill_context_factory, company, branch, db_session, line_count, tmp_path
):
    document, before, builder, _ = bill_context_factory("sales", line_count=line_count)
    document.buyer_phone = "9876543210"
    document.buyer_email = "buyer@example.com"
    document.consignee_phone = "9000000001"
    document.consignee_email = "shipping@example.com"
    document.vehicle_number = "MH 05 XL1995"
    document.lr_number = "4132"
    document.transport_mode = "ROAD"
    db_session.commit()
    db_session.refresh(document)
    context = builder(document, company=company, branch=branch, generated_at=before.generated_at)
    html = build_invoice_html(context)
    sheet_count = len(context.copy_labels) * (1 if line_count == 1 else 2)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.emulate_media(media="print")
            page.set_content(html, wait_until="load")
            sheets = page.locator(".invoice-copy")
            assert sheets.count() == sheet_count
            for sheet in sheets.all():
                panels = sheet.locator(".party-panel")
                assert panels.nth(0).locator(".party-contact").inner_text() == "Contact: 9876543210"
                assert panels.nth(0).locator(".party-email").inner_text() == "Email: buyer@example.com"
                assert panels.nth(1).locator(".party-contact").inner_text() == "Contact: 9000000001"
                assert panels.nth(1).locator(".party-email").inner_text() == "Email: shipping@example.com"
                assert "MH 05 XL1995" not in panels.nth(1).inner_text()
                assert "4132" not in panels.nth(1).inner_text()
                assert sheet.locator(".invoice-meta").inner_text().count("MH 05 XL1995") == 1
                assert sheet.locator(".invoice-meta").inner_text().count("4132") == 1
                fits = panels.evaluate_all("""panels => panels.every(panel => {
                    const rows = [...panel.querySelectorAll('.party-contact, .party-email')];
                    return panel.scrollWidth <= panel.clientWidth + 1
                        && rows.every(row => row.scrollWidth <= row.clientWidth + 1)
                        && rows[0].getBoundingClientRect().bottom <= rows[1].getBoundingClientRect().top + 1;
                })""")
                assert fits
                assert sheet.locator(".party-grid").bounding_box()["y"] < sheet.locator(".items-table").bounding_box()["y"]
        finally:
            browser.close()

    result = render_invoice_pdf(context)
    output = tmp_path / f"sales-party-details-{line_count}.pdf"
    output.write_bytes(result.pdf_bytes)
    metadata = subprocess.run(["pdfinfo", str(output)], check=True, capture_output=True, text=True).stdout
    pages = int(next(line.split(":", 1)[1] for line in metadata.splitlines() if line.startswith("Pages:")))
    assert pages == sheet_count
    subprocess.run(["pdftoppm", "-png", "-scale-to", "1100", str(output), str(output.with_suffix(""))],
                   check=True, capture_output=True)


@pytest.mark.parametrize("kind", ["sales", "reagent", "purchase", "reagent_purchase"])
def test_company_emails_are_saved_on_transaction_and_not_replaced_by_profile_edits(bill_context_factory, kind, branch, company, db_session, client, auth_headers, admin_user):
    document, context, builder, route = bill_context_factory(kind)
    assert context.seller.email_addresses == ("billing@example.com", "orders@example.com")
    branch.email = "new@example.com"
    branch.secondary_email = "new-orders@example.com"
    db_session.commit()
    submitted = client.post(f"{route}/{document.id}/submit", headers=auth_headers(admin_user), json={"expected_version": 1})
    assert submitted.status_code == 200, submitted.text
    approved = client.post(f"{route}/{document.id}/approve", headers=auth_headers(admin_user), json={"expected_version": 1})
    assert approved.status_code == 200, approved.text
    db_session.refresh(document)
    after = builder(document, company=company, branch=branch, generated_at=context.generated_at)
    assert after.seller.email_addresses == context.seller.email_addresses
    html = build_invoice_html(after)
    assert "Pickup Address:" not in html
    assert "new-orders@example.com" not in html
    assert html.count('class="seller-email"') == len(context.copy_labels) * 2
    assert html.count("Add:") == len(context.copy_labels) * 3


@pytest.mark.parametrize("kind", ["sales", "reagent", "purchase", "reagent_purchase"])
@pytest.mark.parametrize("interstate", [False, True])
def test_summary_rates_follow_authoritative_tax_amounts(bill_context_factory, kind, interstate):
    _, context, _, _ = bill_context_factory(kind, interstate=interstate)
    rows = dict(context.tax_rows)
    if interstate:
        assert "IGST @ 18%" in rows
        assert not any(label.startswith(("CGST", "SGST")) for label in rows)
    else:
        assert "CGST @ 9%" in rows and "SGST @ 9%" in rows
        assert not any(label.startswith("IGST") for label in rows)


def test_mixed_tax_summary_lists_each_real_rate_without_changing_saved_amounts(bill_context_factory):
    _, context, _, _ = bill_context_factory("sales", line_count=2, gst_rates=["18.00", "5.00"])
    html = build_invoice_html(context)
    assert "SGST @ 2.5%, 9%" in html
    assert "CGST @ 2.5%, 9%" in html
    assert dict(context.tax_rows)["SGST @ 2.5%, 9%"] == Decimal("11.50")


@pytest.mark.parametrize("kind", ["sales", "reagent", "purchase", "reagent_purchase"])
def test_empty_and_legacy_email_snapshots_do_not_acquire_a_new_second_email(bill_context_factory, kind, branch, company):
    document, context, builder, _ = bill_context_factory(kind)
    document.seller_email_addresses = []
    assert builder(document, company=company, branch=branch, generated_at=context.generated_at).seller.email_addresses == ()
    document.seller_email_addresses = None
    assert builder(document, company=company, branch=branch, generated_at=context.generated_at).seller.email_addresses == ("billing@example.com",)


def test_secondary_email_forward_migration_preserves_issued_documents():
    migration = runpy.run_path(str(Path(__file__).parents[1] / "alembic/versions/20261007_0024_seller_secondary_email.py"))
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE branches (id INTEGER PRIMARY KEY, email TEXT)"))
            connection.execute(text("INSERT INTO branches VALUES (1, 'billing@example.com')"))
            for table in ("invoices", "purchase_orders"):
                connection.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, pdf_storage_key TEXT, final_total NUMERIC(14, 2))"))
                connection.execute(text(f"INSERT INTO {table} VALUES (1, 'issued-original.pdf', 346849.00)"))
            with Operations.context(MigrationContext.configure(connection)):
                migration["upgrade"]()
            assert tuple(connection.execute(text("SELECT email, secondary_email FROM branches")).one()) == ("billing@example.com", None)
            for table in ("invoices", "purchase_orders"):
                row = connection.execute(text(f"SELECT * FROM {table}")).mappings().one()
                assert row["pdf_storage_key"] == "issued-original.pdf"
                assert row["final_total"] == 346849
                assert row["seller_email_addresses"] is None
    finally:
        engine.dispose()


@pytest.mark.parametrize("kind", ["reagent", "reagent_purchase"])
def test_reagent_vehicle_and_column_changes(bill_context_factory, kind):
    _, context, _, _ = bill_context_factory(kind)
    html = build_invoice_html(context)
    meta = html.split('class="meta-detail-stack"', 1)[1].split('class="party-grid"', 1)[0]
    assert meta.rfind("Vehicle No.:") > meta.rfind("Payment Terms:")
    assert "TS09AB1234" in meta
    assert not any("Vehicle No" in line for line in context.consignee.shipment_lines)
    assert '<th scope="col">Per</th>' not in html
    assert '<col style="width: 10%" />' in html
    assert '<div class="item-discount-amount">@ 10.00</div>' in html
    if kind == "reagent_purchase":
        assert context.buyer.heading == "Seller"
        assert context.consignee.heading == "Seller / Shipping Address"


@pytest.mark.parametrize("kind", ["sales", "reagent", "purchase", "reagent_purchase"])
def test_real_render_cell_alignment_email_spacing_and_page_balance(bill_context_factory, kind, tmp_path):
    _, context, _, _ = bill_context_factory(kind)
    html = build_invoice_html(context)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 734, "height": 1100})
            page.set_content(html, wait_until="load")
            page.emulate_media(media="print")
            measurements = page.evaluate("""() => {
                const copy = document.querySelector('.invoice-copy');
                const row = copy.querySelector('.items-table tbody tr');
                const emails = [...copy.querySelectorAll('.seller-email')];
                const secondary = row.querySelector('.item-secondary-line');
                const name = row.querySelector('.item-product-name');
                return {
                    alignments: [...row.cells].map(cell => getComputedStyle(cell).textAlign),
                    descriptionAlignments: [...row.querySelectorAll('.item-product-name, .sales-item-description, .item-secondary-line, .item-tax-row')].map(node => getComputedStyle(node).textAlign),
                    headingAlignments: [...copy.querySelectorAll('.item-heading th')].map(cell => getComputedStyle(cell).textAlign),
                    headings: [...copy.querySelectorAll('.item-heading th')].map(cell => cell.textContent.trim()),
                    emailGap: emails[1].getBoundingClientRect().top - emails[0].getBoundingClientRect().bottom,
                    bodyHeight: copy.querySelector('.items-table tbody').getBoundingClientRect().height,
                    secondaryGap: secondary && secondary.getBoundingClientRect().top - name.getBoundingClientRect().bottom,
                    productSize: name && parseFloat(getComputedStyle(name).fontSize),
                    tableSize: parseFloat(getComputedStyle(row).fontSize),
                    summaryTop: copy.querySelector('.summary-zone').getBoundingClientRect().top,
                    itemsBottom: copy.querySelector('.items-table').getBoundingClientRect().bottom,
                };
            }""")
            pdf = page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            browser.close()
    assert measurements["alignments"][:-1] == ["center", "left"] + ["center"] * (len(measurements["alignments"]) - 3)
    assert all(value == "left" for value in measurements["descriptionAlignments"])
    assert all(value == "center" for value in measurements["headingAlignments"])
    assert measurements["alignments"][-1] == "right"
    assert measurements["emailGap"] >= 0
    assert measurements["summaryTop"] > measurements["itemsBottom"]
    if kind.startswith("reagent"):
        assert "Per" not in measurements["headings"]
        assert measurements["secondaryGap"] >= 4
        assert measurements["productSize"] > measurements["tableSize"]
        assert measurements["bodyHeight"] >= 240  # Shared 64 mm reagent body.
    output = tmp_path / f"{kind}.pdf"
    output.write_bytes(pdf)
    info = subprocess.run(["pdfinfo", str(output)], check=True, capture_output=True, text=True).stdout
    page_count = int(next(line.split(":", 1)[1] for line in info.splitlines() if line.startswith("Pages:")))
    assert page_count == len(context.copy_labels), info
    subprocess.run(["pdftoppm", "-scale-to", "1400", "-png", str(output), str(output.with_suffix(""))], check=True, capture_output=True)
