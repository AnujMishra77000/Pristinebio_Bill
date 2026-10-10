"""Quantity is numeric-only in both reagent PDFs, without changing stored units."""
from dataclasses import replace
from decimal import Decimal
from html.parser import HTMLParser
import subprocess

import pytest
from playwright.sync_api import sync_playwright

from app.services.invoice_pdf import build_invoice_html, render_invoice_pdf
from tests.test_pdf_name_description_style import _context


class ItemCells(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_items = False
        self.in_body = False
        self.in_cell = False
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'table':
            self.in_items = 'items-table' in attributes.get('class', '').split()
        elif self.in_items and tag == 'tbody':
            self.in_body = True
        elif self.in_body and tag == 'tr':
            self.rows.append([])
        elif self.in_body and tag == 'td':
            self.rows[-1].append('')
            self.in_cell = True

    def handle_endtag(self, tag):
        if tag == 'td':
            self.in_cell = False
        elif tag == 'tbody':
            self.in_body = False
        elif tag == 'table':
            self.in_items = False

    def handle_data(self, data):
        if self.in_cell:
            self.rows[-1][-1] += data


@pytest.mark.parametrize('kind', ['reagent', 'reagent_po'])
@pytest.mark.parametrize('unit', ['KG', 'GM', 'ML', 'µg'])
def test_reagent_quantity_cells_show_only_entered_numeric_value(kind, unit):
    context = _context(kind)
    quantities = (Decimal('12.000'), Decimal('0.125'), Decimal('1234.500'))
    context = replace(context, lines=tuple(replace(context.lines[0], serial_number=i, quantity=q, unit=unit)
                                          for i, q in enumerate(quantities, 1)))
    cells = ItemCells()
    cells.feed(build_invoice_html(context))
    assert [row[4].strip() for row in cells.rows] == ['12', '0.125', '1234.5'] * len(context.copy_labels)
    assert all(line.unit == unit for line in context.lines)


@pytest.mark.parametrize('kind', ['sales', 'purchase_order'])
def test_other_bill_quantity_cells_keep_their_existing_units(kind):
    context = _context(kind)
    cells = ItemCells()
    cells.feed(build_invoice_html(context))
    assert [row[3].strip() for row in cells.rows] == ['10KGS'] * len(context.copy_labels)


@pytest.mark.parametrize('kind', ['reagent', 'reagent_po', 'sales', 'purchase_order'])
def test_quantity_bold_only_for_reagents_without_font_size_change(kind):
    context = _context(kind)
    index = 4 if kind.startswith('reagent') else 3
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(build_invoice_html(context), wait_until='load')
            styles = page.locator('.items-table tbody tr').evaluate_all("""(rows, index) => rows.map(row => {
                const cell = row.cells[index];
                const value = cell.firstElementChild;
                return {weight: getComputedStyle(value).fontWeight,
                    size: getComputedStyle(value).fontSize,
                    originalSize: getComputedStyle(cell).fontSize};
            })""", index)
        finally:
            browser.close()
    assert all(style['weight'] == ('700' if kind.startswith('reagent') else '400') for style in styles)
    assert all(style['size'] == style['originalSize'] for style in styles)


@pytest.mark.parametrize('kind', ['reagent', 'reagent_po'])
def test_reagent_numeric_quantity_pdf_renders_without_layout_changes(kind, tmp_path):
    context = _context(kind)
    result = render_invoice_pdf(context)
    output = tmp_path / f'{kind}-numeric-quantity.pdf'
    output.write_bytes(result.pdf_bytes)
    metadata = subprocess.run(['pdfinfo', str(output)], check=True, capture_output=True, text=True).stdout
    assert int(next(line.split(':', 1)[1] for line in metadata.splitlines() if line.startswith('Pages:'))) == len(context.copy_labels)
    subprocess.run(['pdftoppm', '-f', '1', '-singlefile', '-scale-to', '1300', '-png', str(output), str(output.with_suffix(''))],
                   check=True, capture_output=True)
    assert output.with_suffix('.png').is_file()
