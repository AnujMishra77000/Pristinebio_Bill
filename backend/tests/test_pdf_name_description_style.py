"""Regression coverage for approved Sales and Reagent item presentation."""
from dataclasses import replace
from decimal import Decimal
import subprocess

import pytest
from playwright.sync_api import sync_playwright

from app.services.invoice_pdf import (
    COPY_LABELS, TEMPLATE_VERSION, PURCHASE_ORDER_TEMPLATE_VERSION,
    REAGENT_BILL_TEMPLATE_VERSION, REAGENT_PURCHASE_ORDER_TEMPLATE_VERSION,
    build_invoice_html, render_invoice_pdf,
)
from tests.test_invoice_pdf import _fixture_context


def _context(kind):
    base = _fixture_context(1)
    line = replace(base.lines[0], product_name='Bottom Oil', description='Refined industrial oil.\nSuitable for processing.',
                   manufacturer_name='Sigma', article_no='SIG-100', cgst_rate=Decimal('9.00'),
                   sgst_rate=Decimal('9.00'), cgst_amount=Decimal('27.00'), sgst_amount=Decimal('27.00'))
    versions = {'sales': TEMPLATE_VERSION, 'reagent': REAGENT_BILL_TEMPLATE_VERSION,
                'purchase_order': PURCHASE_ORDER_TEMPLATE_VERSION, 'reagent_po': REAGENT_PURCHASE_ORDER_TEMPLATE_VERSION}
    is_po = kind in ('purchase_order', 'reagent_po')
    # Domestic PO intentionally retains its material-name-only item presentation.
    if kind == 'purchase_order':
        line = replace(line, description='Bottom Oil')
    return replace(base, lines=(line,), document_type='reagent' if kind == 'reagent_po' else kind,
                   template_version=versions[kind],
                   document_title='Purchase Order' if is_po else 'Tax Invoice',
                   document_number_label='PO No' if is_po else 'Invoice No',
                   copy_labels=('Purchase Order',) if is_po else COPY_LABELS)


@pytest.mark.parametrize('kind', ['sales', 'reagent', 'purchase_order', 'reagent_po'])
def test_sales_and_po_party_names_are_bold_while_all_formats_still_wrap(kind):
    context = _context(kind)
    context = replace(context,
                      buyer=replace(context.buyer, name='Buyer Industrial Chemicals and Raw Materials Trading Private Limited ' * 2),
                      consignee=replace(context.consignee, name='Consignee Research Laboratory and Industrial Processing Centre ' * 2))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.emulate_media(media='print')
            page.set_content(build_invoice_html(context), wait_until='load')
            names = page.locator('.party-name').evaluate_all("""nodes => nodes.map(node => ({
                weight: getComputedStyle(node).fontWeight,
                fits: node.scrollWidth <= node.clientWidth + 1,
                panelFits: node.parentElement.scrollHeight <= node.parentElement.clientHeight + 1,
            }))""")
            address_weights = page.locator('.party-line').evaluate_all('nodes => nodes.map(node => getComputedStyle(node).fontWeight)')
        finally:
            browser.close()
    assert len(names) == len(context.copy_labels) * 2
    weight = '400' if kind == 'reagent' else '700'
    assert all(name == {'weight': weight, 'fits': True, 'panelFits': True} for name in names)
    assert address_weights and all(weight != '700' for weight in address_weights)


def test_sales_item_has_bold_name_above_smaller_regular_entered_description():
    context = _context('sales')
    line = replace(context.lines[0], description='Refined <oil> & processing grade.\nSecond specification line.' + ' Quality specification' * 18)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.emulate_media(media='print')
            page.set_content(build_invoice_html(replace(context, lines=(line,))), wait_until='load')
            cell = page.locator('.sales-items-table .item-description').first
            name = cell.locator('.item-product-name')
            description = cell.locator('.sales-item-description')
            assert name.count() == 1
            assert description.count() == 1
            assert name.inner_text() == 'Bottom Oil'
            assert description.inner_text() == line.description
            assert cell.locator('oil').count() == 0  # entered markup remains plain text
            style = cell.evaluate("""cell => {
                const name = cell.querySelector('.item-product-name');
                const description = cell.querySelector('.sales-item-description');
                return {nameWeight: getComputedStyle(name).fontWeight, descriptionWeight: getComputedStyle(description).fontWeight,
                    smaller: parseFloat(getComputedStyle(description).fontSize) < parseFloat(getComputedStyle(name).fontSize),
                    below: description.getBoundingClientRect().top >= name.getBoundingClientRect().bottom - 1,
                    fits: cell.scrollWidth <= cell.clientWidth + 1,
                    preservesLines: getComputedStyle(description).whiteSpace === 'pre-line'};
            }""")
        finally:
            browser.close()
    assert style == {'nameWeight': '700', 'descriptionWeight': '400', 'smaller': True,
                     'below': True, 'fits': True, 'preservesLines': True}


@pytest.mark.parametrize('description', ['', '   ', 'Bottom Oil'])
def test_sales_name_only_item_does_not_add_blank_or_duplicate_description(description):
    context = _context('sales')
    html = build_invoice_html(replace(context, lines=(replace(context.lines[0], description=description),)))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until='load')
            cells = page.locator('.sales-items-table .item-description')
            assert cells.all_inner_texts() == ['Bottom Oil'] * len(COPY_LABELS)
            assert cells.locator('.sales-item-description').count() == 0
        finally:
            browser.close()


@pytest.mark.parametrize('kind', ['reagent', 'reagent_po'])
def test_reagent_secondary_line_labels_saved_manufacturer_without_empty_prefixes(kind):
    context = _context(kind)
    cases = [
        ('Sigma', 'SIG', 'SIG-100', 'MFG: Sigma, Artical No.: SIG-100'),
        (None, 'MRK', 'MRK-200', 'MFG: MRK, Artical No.: MRK-200'),
        ('Sigma', None, None, 'MFG: Sigma'),
        (None, None, 'RX-300', 'Artical No.: RX-300'),
        (None, None, None, None),
    ]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.emulate_media(media='print')
            for name, code, article, expected in cases:
                line = replace(context.lines[0], manufacturer_name=name,
                               manufacturer_code=code, article_no=article)
                page.set_content(build_invoice_html(replace(context, lines=(line,))), wait_until='load')
                secondary = page.locator('.reagent-items-table .item-secondary-line')
                assert secondary.all_inner_texts() == ([expected] * len(context.copy_labels) if expected else [])
                if expected:
                    style = secondary.first.evaluate("""node => ({
                        weight: getComputedStyle(node).fontWeight,
                        size: parseFloat(getComputedStyle(node).fontSize),
                        nameSize: parseFloat(getComputedStyle(node.previousElementSibling).fontSize),
                        nameWeight: getComputedStyle(node.previousElementSibling).fontWeight,
                    })""")
                    assert style['weight'] == '400'
                    assert style['nameWeight'] == '700'
                    assert style['size'] == pytest.approx(style['nameSize'] * 0.85, abs=0.01)
        finally:
            browser.close()


@pytest.mark.parametrize('kind', ['reagent', 'reagent_po'])
def test_reagent_long_secondary_metadata_wraps_above_gst_and_renders_to_pdf(tmp_path, kind):
    context = _context(kind)
    # Test long MFG wrapping without unrelated optional export/acknowledgement
    # rows consuming the entire printable page before the product begins.
    context = replace(context, irn=None, e_way_bill_number=None, e_way_bill_date=None,
                      acknowledgement_number=None, po_date=None)
    line = replace(context.lines[0], manufacturer_name='Sigma <Research> & Laboratory Chemicals ' * 4,
                   article_no='SIG-' + '1234567890' * 6, pack_size='500 g')
    context = replace(context, lines=(line,))
    html = build_invoice_html(context)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.emulate_media(media='print')
            page.set_content(html, wait_until='load')
            cell = page.locator('.reagent-items-table .item-description').first
            assert cell.locator('.item-secondary-line').inner_text() == f'MFG: {line.manufacturer_name}, Artical No.: {line.article_no}'
            assert cell.locator('Research').count() == 0
            layout = cell.evaluate("""cell => {
                const name = cell.querySelector('.item-product-name').getBoundingClientRect();
                const secondary = cell.querySelector('.item-secondary-line');
                const secondaryBox = secondary.getBoundingClientRect();
                const tax = cell.querySelector('.item-tax-breakdown');
                return {belowName: secondaryBox.top >= name.bottom - 1,
                    taxBelowMetadata: tax.getBoundingClientRect().top >= secondaryBox.bottom - 1,
                    wraps: secondaryBox.height > parseFloat(getComputedStyle(secondary).lineHeight) * 2,
                    fits: cell.scrollWidth <= cell.clientWidth + 1,
                    taxWeight: getComputedStyle(tax).fontWeight};
            }""")
        finally:
            browser.close()
    assert layout == {'belowName': True, 'taxBelowMetadata': True, 'wraps': True,
                      'fits': True, 'taxWeight': '700'}
    output = tmp_path / f'{kind}-long-mfg.pdf'
    output.write_bytes(render_invoice_pdf(context).pdf_bytes)
    info = subprocess.run(['pdfinfo', str(output)], capture_output=True, text=True, check=True).stdout
    assert '(A4)' in info
    subprocess.run(['pdftoppm', '-f', '1', '-singlefile', '-scale-to', '1400', '-png', str(output), str(output.with_suffix(''))],
                   capture_output=True, check=True)
    assert output.with_suffix('.png').exists()


@pytest.mark.parametrize('kind', ['sales', 'reagent', 'purchase_order', 'reagent_po'])
def test_style_fixtures_render_with_existing_format_specific_items(tmp_path, kind):
    context = _context(kind)
    html = build_invoice_html(context)
    if kind != 'sales':
        assert '<div class="sales-item-description"' not in html
    output = tmp_path / f'{kind}-name-description.pdf'
    output.write_bytes(render_invoice_pdf(context).pdf_bytes)
    info = subprocess.run(['pdfinfo', str(output)], capture_output=True, text=True, check=True).stdout
    metadata = {line.split(':', 1)[0]: line.split(':', 1)[1].strip() for line in info.splitlines() if ':' in line}
    assert '(A4)' in metadata['Page size']
    # A converted fixture can continue to a second page; the existing real
    # Sales/Reagent-PO short-document tests assert their one-page contracts.
    assert int(metadata['Pages']) >= len(context.copy_labels)
    assert int(metadata['Pages']) % len(context.copy_labels) == 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until='load')
            names = page.locator('.party-name').all_inner_texts()
            items = page.locator('.item-description').all_inner_texts()
        finally:
            browser.close()
    assert names.count('Buyer Example') == len(context.copy_labels)
    assert names.count('Consignee Example') == len(context.copy_labels)
    assert len(items) == len(context.copy_labels)
    assert all('Bottom Oil' in item for item in items)
    if kind == 'sales':
        assert all('Refined industrial oil.' in item for item in items)
    elif kind in ('reagent', 'reagent_po'):
        assert all('Sigma, Artical No.: SIG-100' in item and 'CGST 9%' in item for item in items)
    else:
        assert all('Refined industrial oil.' not in item for item in items)
    subprocess.run(['pdftoppm', '-f', '1', '-singlefile', '-scale-to', '1400', '-png', str(output), str(output.with_suffix(''))],
                   capture_output=True, check=True)
    assert output.with_suffix('.png').exists()
