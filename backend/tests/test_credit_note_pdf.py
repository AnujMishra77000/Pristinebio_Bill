"""Real Chromium preview/final rendering, metadata and physical page checks."""
import hashlib
import os
from pathlib import Path
import subprocess

import pytest
from playwright.sync_api import Page

from app.core.config import get_settings
from tests.test_credit_notes import _approve, _create, _payload


@pytest.mark.parametrize("item_count", [1, 6])
def test_credit_note_pdf_preview_confirm_download_and_page_layout(
    item_count, client, auth_headers, staff_user, manager_user, branch, monkeypatch, tmp_path,
):
    payload = _payload(client, auth_headers, staff_user, branch)
    payload["lines"] = [{**payload["lines"][0], "quantity": "1.000", "product_name": f"Reagent {index}", "description": f"Reagent item description {index}"} for index in range(1, item_count + 1)]
    branch.bank_name = "Example Bank"
    branch.bank_account_name = "Example Company"
    branch.bank_account_number = "TEST123456"
    branch.bank_ifsc_code = "TEST0000001"
    note = _create(client, auth_headers(staff_user), payload)
    path = f"/api/v1/invoices/{note['id']}"
    monkeypatch.setattr(get_settings(), "pdf_storage_dir", str(tmp_path))
    chromium_pdf = Page.pdf
    rendered = []

    def inspect(page, *args, **kwargs):
        rendered.append(page.locator(".invoice-page").evaluate_all("""pages => pages.map(p => {
            const box = p.getBoundingClientRect(), footer = p.querySelector('.invoice-footer').getBoundingClientRect();
            const terms = p.querySelector('.terms').getBoundingClientRect(), signature = p.querySelector('.signature').getBoundingClientRect();
            return {
                rows: p.querySelectorAll('.items-table tbody tr').length,
                words: p.querySelector('.amount-words-line > span:last-child').textContent.trim(),
                title: p.querySelector('.invoice-title').textContent.trim(),
                bank: p.querySelector('.bank-details-footer').textContent,
                fits: Math.max(terms.bottom, signature.bottom) <= footer.top + 1 && footer.bottom <= box.bottom + 1,
            };
        })"""))
        return chromium_pdf(page, *args, **kwargs)

    monkeypatch.setattr(Page, "pdf", inspect)
    preview = client.post(path + "/preview-pdf", headers=auth_headers(staff_user), json={"expected_version": note["version"]})
    assert preview.status_code == 200, preview.text[:300] if preview.status_code != 200 else ""
    assert preview.content.startswith(b"%PDF")
    assert preview.headers["cache-control"] == "no-store"
    still_draft = client.get(path, headers=auth_headers(staff_user)).json()
    assert still_draft["status"] == "draft"
    assert still_draft["pdf_storage_key"] is None
    _approve(client, auth_headers, staff_user, manager_user, note)
    generated = client.post(path + "/generate-pdf", headers=auth_headers(manager_user))
    assert generated.status_code == 200, generated.text
    confirmed = generated.json()
    assert confirmed["status"] == "pdf_generated"
    assert confirmed["pdf_template_version"] == "a4-credit-note-v2"
    assert confirmed["pdf_generated_by_id"] == manager_user.id
    assert confirmed["pdf_generated_at"]
    downloaded = client.get(path + "/pdf", headers=auth_headers(staff_user))
    assert downloaded.status_code == 200
    assert hashlib.sha256(downloaded.content).hexdigest() == confirmed["pdf_sha256"]
    replay = client.post(path + "/generate-pdf", headers=auth_headers(manager_user))
    assert replay.json()["pdf_sha256"] == confirmed["pdf_sha256"]
    assert len(rendered) == 2  # Repeated confirmation must not regenerate it.
    pages_per_copy = 1 if item_count == 1 else 2
    for pages in rendered:
        assert len(pages) == 4 * pages_per_copy
        assert [p["rows"] for p in pages] == ([1] * 4 if item_count == 1 else [3, 3] * 4)
        assert all(p["title"] == "Credit Note" and p["fits"] for p in pages)
        assert all("TEST123456" in p["bank"] for p in pages)
        assert all(bool(p["words"]) == (index % pages_per_copy == pages_per_copy - 1) for index, p in enumerate(pages))
    output = Path(os.environ.get("CREDIT_NOTE_PDF_OUTPUT", tmp_path))
    output.mkdir(parents=True, exist_ok=True)
    pdf = output / f"credit-note-{item_count}-items.pdf"
    pdf.write_bytes(downloaded.content)
    subprocess.run(["pdftoppm", "-r", "80", "-png", str(pdf), str(pdf.with_suffix(""))], check=True, capture_output=True)
    assert len(list(output.glob(f"credit-note-{item_count}-items-*.png"))) == 4 * pages_per_copy
