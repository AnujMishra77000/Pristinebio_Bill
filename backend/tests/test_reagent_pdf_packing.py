"""Reagent overflow must not strand displaced products on singleton sheets."""
from dataclasses import replace
import subprocess

import pytest
from playwright.sync_api import Page

from app.services.invoice_pdf import render_invoice_pdf
from tests.test_bill_header_tax_layout import bill_context_factory


def tall_reagent_context(factory, line_count=6):
    _, context, _, _ = factory("reagent", line_count=line_count)
    address = (
        "Industrial laboratory research estate, building 170, chemical analysis department, Maharashtra, India",
        "Technical knowledge park, fourth floor, analytical laboratory research road, industrial east campus",
        "Mumbai, Maharashtra - 400001",
    )
    party = dict(name="Synthetic Laboratory Company", address_lines=address,
                 pan="ABCDE1234F", contact="9000000000", email=None)
    return replace(context,
        buyer=replace(context.buyer, **party),
        consignee=replace(context.consignee, **party),
        lines=tuple(replace(line,
            product_name=f"Analytical hydrogen phosphate laboratory material {index + 1}",
            manufacturer_name="LAB", article_no=f"1.01234.0{index + 1:03}")
            for index, line in enumerate(context.lines)),
    )


@pytest.mark.parametrize("line_count", [6, 9])
def test_reagent_overflow_reuses_space_on_following_sheets(
    bill_context_factory, monkeypatch, tmp_path, line_count,
):
    context = tall_reagent_context(bill_context_factory, line_count)
    sheets = []
    chromium_pdf = Page.pdf

    def inspect(page, *args, **kwargs):
        sheets.extend(page.locator(".invoice-page").evaluate_all("""pages => pages.map(p => {
            const bounds = p.getBoundingClientRect();
            const box = selector => p.querySelector(selector).getBoundingClientRect();
            const table = box('.items-table'), summary = box('.summary-zone');
            const footer = box('.invoice-footer'), terms = box('.terms'), signature = box('.signature');
            return {
                serials: [...p.querySelectorAll('.items-table tbody tr')].map(r => Number(r.cells[0].textContent.trim())),
                label: p.querySelector('.copy-label').textContent.trim(),
                words: p.querySelector('.amount-words-line > span:last-child').textContent.trim(),
                quantity: p.querySelector('.total-quantity').textContent.replace('Total Quantity:', '').trim(),
                totals: [...p.querySelectorAll('.tax-summary td:last-child')].map(td => td.textContent.trim()),
                terms: p.querySelectorAll('.terms-list li').length,
                fits: summary.top >= table.bottom && Math.max(terms.bottom, signature.bottom) <= footer.top + 1 && footer.bottom <= bounds.bottom + 1,
                bank: !!p.querySelector('.bank-details-footer'),
            };
        })"""))
        return chromium_pdf(page, *args, **kwargs)

    monkeypatch.setattr(Page, "pdf", inspect)
    result = render_invoice_pdf(context)
    # Persist diagnostics even when the old singleton packing assertion fails.
    output = tmp_path / f"{line_count}-reagent-products.pdf"
    output.write_bytes(result.pdf_bytes)
    pages_per_copy = line_count // 3
    expected = [list(range(start, start + 3)) for start in range(1, line_count + 1, 3)]
    assert len(sheets) == pages_per_copy * len(context.copy_labels), [s["serials"] for s in sheets]
    for start in range(0, len(sheets), pages_per_copy):
        copy = sheets[start:start + pages_per_copy]
        assert [s["serials"] for s in copy] == expected
        assert not any(s["words"] for s in copy[:-1])
        assert copy[-1]["words"] == context.amount_in_words
        assert {s["label"] for s in copy} == {context.copy_labels[start // pages_per_copy]}
        assert not any(s["quantity"] or any(s["totals"]) for s in copy[:-1])
        assert copy[-1]["quantity"] == str(line_count)
        assert all(copy[-1]["totals"])
        assert copy[-1]["totals"][-1] == f"{context.final_total:,.2f}"
    assert all(s["fits"] and s["bank"] and s["terms"] >= 4 for s in sheets)
    info = subprocess.run(["pdfinfo", str(output)], check=True, capture_output=True, text=True).stdout
    assert f"Pages:           {len(sheets)}" in info
    subprocess.run(["pdftoppm", "-f", "1", "-l", str(pages_per_copy), "-png", "-scale-to", "1300", str(output), str(output.with_suffix(""))], check=True, capture_output=True)
