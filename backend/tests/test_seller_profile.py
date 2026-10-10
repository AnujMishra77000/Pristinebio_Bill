from app.core.security import hash_password
from app.models.company import Branch, Company
from app.models.enums import UserRole
from app.models.user import User, UserBranchAssignment


def _profile_payload(**overrides):
    payload = {
        "legal_name": "Pristine Biopharma Private Limited",
        "trade_name": "Pristine Biopharma",
        "pan": "AAAAA0000A",
        "registered_address": "1 Industrial Estate, Hyderabad",
        "seller_name": "Primary Seller Profile",
        "gstin": "36ABCDE1234F1Z5",
        "address_line1": "1 Industrial Estate",
        "address_line2": "Building A",
        "city": "Hyderabad",
        "state": "Telangana",
        "state_code": "36",
        "postal_code": "500001",
        "phone": "9000000000",
        "email": "billing@pristine.example",
        "bank_name": "ICICI Bank",
        "bank_branch_name": "Gurugram Sector Forty Four",
        "bank_account_name": "Pristine Biopharma",
        "bank_account_number": "777705889826",
        "bank_ifsc_code": "ICIC0005961",
        "terms_body": "Insurance at seller's account.\nPayment by bank transfer only.",
        "is_active": True,
    }
    payload.update(overrides)
    return payload


def _unassigned_staff(db_session):
    user = User(
        email="unassigned-staff@example.com",
        full_name="Unassigned Staff",
        role=UserRole.STAFF,
        hashed_password=hash_password("Abc123"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_second_email_can_be_saved_reloaded_edited_and_cleared(client, auth_headers, admin_user):
    payload = _profile_payload(secondary_email="orders@pristine.example")
    response = client.put("/api/v1/companies/profile", headers=auth_headers(admin_user), json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["seller_profile"]["secondary_email"] == "orders@pristine.example"
    assert client.get("/api/v1/companies/profile", headers=auth_headers(admin_user)).json()["seller_profile"]["secondary_email"] == "orders@pristine.example"
    for value in ("new-orders@pristine.example", None):
        response = client.patch(f'/api/v1/branches/{response.json()["seller_profile"]["id"]}', headers=auth_headers(admin_user), json={"secondary_email": value})
        assert response.status_code == 200, response.text
        assert response.json()["secondary_email"] == value
        response = client.get("/api/v1/companies/profile", headers=auth_headers(admin_user))


def test_second_email_is_validated_and_admin_only(client, auth_headers, admin_user, staff_user, branch):
    response = client.put("/api/v1/companies/profile", headers=auth_headers(admin_user), json=_profile_payload(secondary_email="invalid email"))
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "secondary_email"
    assert client.patch(f"/api/v1/branches/{branch.id}", headers=auth_headers(staff_user), json={"secondary_email": "orders@example.com"}).status_code == 403


def test_omitted_second_email_preserves_saved_value_and_changes_are_audited(client, auth_headers, admin_user, branch, db_session):
    from sqlalchemy import select
    from app.models.authentication import SecurityAudit

    response = client.put("/api/v1/companies/profile", headers=auth_headers(admin_user), json=_profile_payload(secondary_email="orders@pristine.example"))
    assert response.status_code == 200, response.text
    record = db_session.scalar(select(SecurityAudit).where(SecurityAudit.action == "seller_profile_updated").order_by(SecurityAudit.id.desc()))
    assert record.actor_id == admin_user.id and record.created_at
    assert record.before["seller_profile"]["secondary_email"] is None
    assert record.after["seller_profile"]["secondary_email"] == "orders@pristine.example"
    response = client.put("/api/v1/companies/profile", headers=auth_headers(admin_user), json=_profile_payload())
    assert response.status_code == 200, response.text
    assert response.json()["seller_profile"]["secondary_email"] == "orders@pristine.example"


def test_admin_can_create_first_company_and_seller_profile_atomically(
    client, auth_headers, db_session, admin_user
):

    response = client.put(
        "/api/v1/companies/profile",
        headers=auth_headers(admin_user),
        json=_profile_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["company"]["legal_name"] == "Pristine Biopharma Private Limited"
    assert body["seller_profile"]["gstin"] == "36ABCDE1234F1Z5"
    assert body["seller_profile"]["bank_name"] == "ICICI Bank"
    assert body["seller_profile"]["bank_account_number"] == "777705889826"
    assert body["seller_profile"]["terms_body"] == "Insurance at seller's account.\nPayment by bank transfer only."
    assert db_session.query(Company).count() == 1
    assert db_session.query(Branch).count() == 1
    assert db_session.query(UserBranchAssignment).filter_by(user_id=admin_user.id).count() == 0
    saved_branch = db_session.query(Branch).one()
    assert saved_branch.bank_ifsc_code == "ICIC0005961"


def test_admin_can_edit_seller_profile(
    client, auth_headers, admin_user, branch, company
):
    response = client.put(
        "/api/v1/companies/profile",
        headers=auth_headers(admin_user),
        json=_profile_payload(trade_name="Pristine Bio Updated", seller_name="Updated GST Profile"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["company"]["trade_name"] == "Pristine Bio Updated"
    assert body["seller_profile"]["name"] == "Updated GST Profile"
    assert body["seller_profile"]["id"] == branch.id
    assert body["company"]["id"] == company.id


def test_staff_cannot_edit_a_profile_without_an_authorized_branch(
    client, auth_headers, db_session, branch, company
):
    staff = _unassigned_staff(db_session)

    response = client.put(
        "/api/v1/companies/profile",
        headers=auth_headers(staff),
        json=_profile_payload(),
    )

    assert response.status_code == 403


def test_seller_profile_validates_gstin(client, auth_headers, admin_user):
    response = client.put(
        "/api/v1/companies/profile",
        headers=auth_headers(admin_user),
        json=_profile_payload(gstin="INVALID"),
    )

    assert response.status_code == 422
