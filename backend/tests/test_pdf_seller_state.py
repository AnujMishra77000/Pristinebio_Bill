"""Seller state belongs in every bill header, never sourced from its recipient."""
import subprocess

import pytest
from playwright.sync_api import sync_playwright

from app.services.invoice_pdf import build_invoice_html
from tests.test_bill_header_tax_layout import bill_context_factory


@pytest.mark.parametrize("kind", ["sales", "reagent", "purchase", "reagent_purchase"])
@pytest.mark.parametrize("code,state", [("27", "Maharashtra"), ("36", "Telangana")])
def test_all_bill_headers_show_seller_state_after_emails(bill_context_factory, kind, code, state, branch, db_session, tmp_path):
    branch.state_code = code
    branch.state = state
    branch.gstin = f"{code}ABCDE1234F1Z5"
    db_session.commit()
    document, context, builder, _ = bill_context_factory(kind)
    html = build_invoice_html(context)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 734, "height": 1100})
            page.emulate_media(media="print")
            page.set_content(html, wait_until="load")
            headers = page.locator(".seller-facts")
            assert headers.count() == len(context.copy_labels)
            for header in headers.all():
                assert header.locator(".seller-state-code").inner_text() == f"State Code: {code}"
                assert header.locator(".seller-state").inner_text() == f"State: {state.upper()}"
                emails = header.locator(".seller-email")
                assert emails.count() == 2
                assert emails.last.bounding_box()["y"] + emails.last.bounding_box()["height"] <= header.locator(".seller-state-code").bounding_box()["y"]
                assert header.locator(".seller-state-code").bounding_box()["y"] < header.locator(".seller-state").bounding_box()["y"]
            pdf = page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            browser.close()
    output = tmp_path / f"{kind}-{code}-seller-state.pdf"
    output.write_bytes(pdf)
    info = subprocess.run(["pdfinfo", str(output)], check=True, capture_output=True, text=True).stdout
    pages = next(int(line.split(":", 1)[1]) for line in info.splitlines() if line.startswith("Pages:"))
    assert pages == len(context.copy_labels), "Two state rows must not introduce an overflow sheet"
    subprocess.run(["pdftoppm", "-f", "1", "-singlefile", "-scale-to", "1400", "-png", str(output), str(output.with_suffix(""))], check=True, capture_output=True)
    # A later profile state/GSTIN change must not replace the recorded code.
    branch.state_code, branch.state = "29", "Karnataka"
    db_session.commit()
    after = builder(document, branch=branch, generated_at=context.generated_at)
    assert after.seller.state_code == code
    if kind in {"sales", "reagent"}:
        assert after.seller.state == state
    else:
        assert after.seller.state is None, "Do not pair saved GSTIN/code with another state's current profile name"
