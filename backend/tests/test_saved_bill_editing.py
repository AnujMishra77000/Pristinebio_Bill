from copy import deepcopy

import pytest
from sqlalchemy import func, select

from app.models.invoice import Invoice, InvoiceRevision
from app.models.purchase_order import PurchaseOrder, PurchaseOrderRevision
from app.models.master_records import Product
from tests.test_inline_submission import DOCUMENTS, _document


@pytest.mark.parametrize("document_type", DOCUMENTS)
def test_saved_draft_edits_keep_one_document_and_enforce_versions_and_final_immutability(
    document_type, client, auth_headers, staff_user, manager_user, branch, db_session,
):
    url, original, payload = _document(document_type, client, auth_headers, staff_user, branch)
    is_po = "purchase-orders" in url
    model, revision_model = (PurchaseOrder, PurchaseOrderRevision) if is_po else (Invoice, InvoiceRevision)
    number_field = "purchase_order_number" if is_po else "invoice_number"
    edited = deepcopy(payload)
    edited["lines"][0]["quantity"] = "2.000"
    edited["payment_terms"] = "Edited terms retained on the same document"
    preview = client.post("/api/v1/purchase-orders/preview" if is_po else "/api/v1/invoices/preview", headers=auth_headers(staff_user), json=edited)
    assert preview.status_code == 200, preview.text
    if is_po:
        field = "reagent_details" if document_type == "reagent_po" else "domestic_details"
        update = {"expected_version": original["version"], field: edited}
    else:
        edited.pop("document_type", None)
        update = {**edited, "expected_version": original["version"]}
    response = client.patch(url, headers=auth_headers(staff_user), json=update)
    assert response.status_code == 200, response.text
    current = response.json()
    assert current["id"] == original["id"]
    assert current[number_field] == original[number_field]
    assert current["version"] == original["version"] + 1
    assert current["lines"][0]["quantity"] == "2.000"
    assert current["payment_terms"] == edited["payment_terms"]
    assert current["final_total"] == preview.json()["final_total"]
    assert db_session.scalar(select(func.count()).select_from(model)) == 1
    assert db_session.scalar(select(func.count()).select_from(revision_model)) == 2
    stale = client.patch(url, headers=auth_headers(staff_user), json=update)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"
    submitted = client.post(url + "/submit", headers=auth_headers(staff_user), json={"expected_version": current["version"]})
    assert submitted.status_code == 200
    approved = client.post(url + "/approve", headers=auth_headers(manager_user), json={"expected_version": submitted.json()["version"]})
    assert approved.status_code == 200, approved.text
    assert approved.json()["final_total"] == current["final_total"]
    update["expected_version"] = approved.json()["version"]
    forbidden = client.patch(url, headers=auth_headers(staff_user), json=update)
    assert forbidden.status_code == 409
    assert db_session.get(model, original["id"]).version == approved.json()["version"]


@pytest.mark.parametrize("document_type", DOCUMENTS)
def test_saved_bill_editing_never_grants_access_to_an_unassigned_profile(
    document_type, client, auth_headers, admin_user, staff_user, other_branch,
):
    url, document, _ = _document(document_type, client, auth_headers, admin_user, other_branch)
    assert client.get(url, headers=auth_headers(staff_user)).status_code == 403
    denied = client.patch(url, headers=auth_headers(staff_user), json={"expected_version": document["version"], "payment_terms": "Unauthorized edit"})
    assert denied.status_code == 403


@pytest.mark.parametrize("document_type", DOCUMENTS)
def test_editing_a_saved_line_preserves_its_explicit_name_without_overwriting_the_product_master(
    document_type, client, auth_headers, staff_user, branch, db_session,
):
    url, document, payload = _document(document_type, client, auth_headers, staff_user, branch)
    product_id = document["lines"][0]["product_id"]
    product = db_session.get(Product, product_id)
    product.name = "Later catalog name"
    db_session.commit()
    edited = deepcopy(payload)
    edited["lines"][0].update(product_id=product_id, product_name="Edited transaction item", rate=document["lines"][0]["rate"], quantity="2.000")
    if "purchase-orders" in url:
        update = {"expected_version": document["version"], "reagent_details" if document_type == "reagent_po" else "domestic_details": edited}
    else:
        edited.pop("document_type", None)
        update = {**edited, "expected_version": document["version"]}
    response = client.patch(url, headers=auth_headers(staff_user), json=update)
    assert response.status_code == 200, response.text
    assert response.json()["lines"][0]["product_name"] == "Edited transaction item"
    assert response.json()["lines"][0]["product_id"] == product_id
    assert db_session.get(Product, product_id).name == "Later catalog name"
