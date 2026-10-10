"""Regression: a fifth product or a closing-only page must never slip through."""

from dataclasses import replace
import math
import subprocess

import pytest
from playwright.sync_api import Page, sync_playwright

from app.services.invoice_pdf import build_invoice_html, render_invoice_pdf
from tests.test_bill_header_tax_layout import bill_context_factory


@pytest.mark.parametrize('kind', ['purchase', 'reagent_purchase', 'sales', 'reagent'])
@pytest.mark.parametrize('line_count', [1, 5])
def test_purchase_orders_have_one_copy_and_invoices_keep_four(bill_context_factory, kind, line_count, tmp_path):
    _, context, _, _ = bill_context_factory(kind, line_count=line_count)
    labels = ('Purchase Order',) if kind in {'purchase', 'reagent_purchase'} else (
        'Original for Recipient', 'Duplicate for Transporter', 'Triplicate for Supplier', 'Extra',
    )
    assert context.copy_labels == labels
    html = build_invoice_html(context)
    assert html.count('class="copy-label"') == len(labels) * (1 if line_count == 1 else 2)
    if kind in {'purchase', 'reagent_purchase'}:
        assert 'Duplicate for Transporter' not in html and 'Triplicate for Supplier' not in html
    output = tmp_path / f'{kind}-{line_count}-copies.pdf'
    output.write_bytes(render_invoice_pdf(context).pdf_bytes)
    metadata = subprocess.run(['pdfinfo', str(output)], check=True, capture_output=True, text=True).stdout
    pages = int(next(line.split(':', 1)[1] for line in metadata.splitlines() if line.startswith('Pages:')))
    assert pages == len(labels) * (1 if line_count == 1 else 2)
    subprocess.run(['pdftoppm', '-png', '-scale-to', '1100', str(output), str(output.with_suffix(''))],
                   check=True, capture_output=True)


@pytest.mark.parametrize("kind", ["sales", "reagent", "purchase", "reagent_purchase"])
@pytest.mark.parametrize("line_count", [4, 5, 8, 10, 15])
def test_four_products_per_physical_page_with_fixed_sections(
    bill_context_factory, kind, line_count, tmp_path, monkeypatch
):
    _, context, _, _ = bill_context_factory(kind, line_count=line_count)
    html = build_invoice_html(context)
    pages_per_copy = math.ceil(line_count / 4)
    expected_rows = [list(range(start, min(start + 4, line_count + 1)))
                     for start in range(1, line_count + 1, 4)]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 734, "height": 1100})
            page.emulate_media(media="print")
            page.set_content(html, wait_until="load")
            sheets = page.locator(".invoice-copy").evaluate_all("""copies => copies.map(copy => {
                const box = copy.getBoundingClientRect();
                const rect = selector => copy.querySelector(selector).getBoundingClientRect();
                const footer = rect('.invoice-footer');
                const terms = rect('.terms');
                const signature = rect('.signature');
                const summary = rect('.summary-zone');
                const items = rect('.items-table');
                return {
                    label: copy.querySelector('.copy-label').textContent.trim(),
                    serials: [...copy.querySelectorAll('.items-table tbody tr')]
                        .map(row => Number(row.cells[0].textContent.trim())),
                    words: copy.querySelector('.amount-words-line > span:last-child').textContent.trim(),
                    quantity: copy.querySelector('.total-quantity').textContent.replace('Total Quantity:', '').trim(),
                    amounts: [...copy.querySelectorAll('.tax-summary tr td:last-child')]
                        .map(cell => cell.textContent.trim()),
                    bank: !!copy.querySelector('.bank-details-footer'),
                    complete: summary.top > items.bottom &&
                        Math.min(terms.top, signature.top) >= summary.bottom - 1 &&
                        Math.max(terms.bottom, signature.bottom) <= footer.top + 1 &&
                        footer.bottom <= box.top + 283 * 96 / 25.4 + 1,
                };
            })""")
        finally:
            browser.close()
    assert len(sheets) == pages_per_copy * len(context.copy_labels)
    for copy_index, label in enumerate(context.copy_labels):
        copy_sheets = sheets[copy_index * pages_per_copy:(copy_index + 1) * pages_per_copy]
        assert [sheet["serials"] for sheet in copy_sheets] == expected_rows
        for index, sheet in enumerate(copy_sheets):
            assert sheet["label"] == label
            assert sheet["bank"] and sheet["complete"], sheet
            if index == pages_per_copy - 1:
                assert sheet["words"] == context.amount_in_words
                assert sheet["quantity"] and all(sheet["amounts"])
            else:
                assert not sheet["words"] and not sheet["quantity"]
                assert sheet["amounts"] and not any(sheet["amounts"])

    # Inspect the REAL renderer page at the PDF boundary, after its measured-fit
    # normalization. Delegate to Chromium unchanged; this is not a fake PDF.
    emitted = []
    chromium_pdf = Page.pdf

    def inspect_pdf(page, *args, **kwargs):
        emitted.extend(page.locator('.invoice-page').evaluate_all("""sheets => sheets.map(sheet => {
            const box = sheet.getBoundingClientRect();
            const table = sheet.querySelector('.items-table').getBoundingClientRect();
            const summary = sheet.querySelector('.summary-zone').getBoundingClientRect();
            const footer = sheet.querySelector('.invoice-footer').getBoundingClientRect();
            return {serials: [...sheet.querySelectorAll('.items-table tbody tr')].map(r => Number(r.cells[0].textContent.trim())),
                tableDepth: table.bottom - box.top, summaryDepth: summary.top - box.top,
                fits: footer.bottom <= box.bottom + 1 && summary.top > table.bottom};
        })"""))
        return chromium_pdf(page, *args, **kwargs)

    monkeypatch.setattr(Page, 'pdf', inspect_pdf)
    result = render_invoice_pdf(context)
    assert [sheet['serials'] for sheet in emitted] == expected_rows * len(context.copy_labels)
    assert all(sheet['fits'] for sheet in emitted)
    assert max(sheet['tableDepth'] for sheet in emitted) - min(sheet['tableDepth'] for sheet in emitted) <= 1
    assert max(sheet['summaryDepth'] for sheet in emitted) - min(sheet['summaryDepth'] for sheet in emitted) <= 1
    output = tmp_path / f"{kind}-{line_count}.pdf"
    output.write_bytes(result.pdf_bytes)
    output.with_suffix(".html").write_text(html, encoding="utf-8")
    info = subprocess.run(["pdfinfo", str(output)], check=True, capture_output=True, text=True).stdout
    physical_pages = int(next(line.split(":", 1)[1] for line in info.splitlines() if line.startswith("Pages:")))
    assert physical_pages == len(sheets), info
    subprocess.run(["pdftoppm", "-png", "-scale-to", "1100", str(output), str(output.with_suffix(""))],
                   check=True, capture_output=True)


def test_unprintably_large_fixed_content_fails_instead_of_clipping(bill_context_factory):
    _, context, _, _ = bill_context_factory("reagent_purchase")
    context = replace(context, terms=("Very long terms " * 2000,))
    with pytest.raises(RuntimeError, match="fit.*A4"):
        render_invoice_pdf(context)


def test_long_products_split_without_rejecting_the_singleton_final_page(bill_context_factory, monkeypatch, tmp_path):
    _, context, _, _ = bill_context_factory('reagent_purchase', line_count=5)
    context = replace(context, lines=tuple(replace(line, product_name=line.product_name + ' analytical laboratory specification' * 4)
                                          for line in context.lines))
    rows = []
    chromium_pdf = Page.pdf

    def inspect_pdf(page, *args, **kwargs):
        rows.extend(page.locator('.invoice-page').evaluate_all("""sheets => sheets.map(s =>
            [...s.querySelectorAll('.items-table tbody tr')].map(r => Number(r.cells[0].textContent.trim())))"""))
        return chromium_pdf(page, *args, **kwargs)

    monkeypatch.setattr(Page, 'pdf', inspect_pdf)
    result = render_invoice_pdf(context)
    per_copy = len(rows) // len(context.copy_labels)
    assert per_copy > 2  # At least one original four-product group needed splitting.
    for start in range(0, len(rows), per_copy):
        assert [serial for sheet in rows[start:start + per_copy] for serial in sheet] == [1, 2, 3, 4, 5]
    assert all(1 <= len(sheet) <= 4 for sheet in rows)
    output = tmp_path / 'long-products.pdf'
    output.write_bytes(result.pdf_bytes)
    info = subprocess.run(['pdfinfo', str(output)], check=True, capture_output=True, text=True).stdout
    assert int(next(line.split(':', 1)[1] for line in info.splitlines() if line.startswith('Pages:'))) == len(rows)


@pytest.mark.parametrize('kind', ['sales', 'reagent', 'purchase', 'reagent_purchase'])
def test_oversized_pdf_returns_actionable_error_without_finalizing_bill(
    bill_context_factory, kind, branch, db_session, client, auth_headers, admin_user
):
    document, _, _, route = bill_context_factory(kind)
    branch.terms_body = 'Oversized terms ' * 2000
    if hasattr(document, 'terms_body'):
        document.terms_body = branch.terms_body
    db_session.commit()
    response = client.post(f'{route}/{document.id}/preview-pdf', headers=auth_headers(admin_user),
                           json={'expected_version': document.version})
    assert response.status_code == 422, response.text
    assert 'fit on A4' in response.json()['detail']
    db_session.refresh(document)
    assert document.status == 'draft' and document.pdf_storage_key is None
