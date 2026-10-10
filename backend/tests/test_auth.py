"""Authentication contract smoke tests; security lifecycle is tested separately."""
import pytest
from app.core.config import get_settings
from app.services.account_security import now
from test_session_security import sign_in, PASSPHRASE


def test_login_normalizes_email_case(client,staff_user):
    response=client.post("/api/v1/auth/login",json={"email":staff_user.email.upper(),"password":"Abc123"})
    assert response.status_code==200 and response.json()["user"]["email"]==staff_user.email


def test_all_roles_use_the_same_sign_in(client, staff_user, manager_user, admin_user):
    for user in (staff_user, manager_user, admin_user):
        response = client.post("/api/v1/auth/login", json={"email": user.email, "password": "Abc123"})
        assert response.status_code == 200
        assert response.json()["user"]["role"] == user.role.value
        client.cookies.clear()


@pytest.mark.parametrize("password",["wrong", "a"*128])
def test_wrong_password_has_safe_error(client,staff_user,password):
    response=client.post("/api/v1/auth/login",json={"email":staff_user.email,"password":password})
    assert response.status_code==401 and "credentials" in response.json()["detail"]


def test_login_bounds_input_and_rejects_role_injection(client,staff_user):
    for extra in ({"password":"a"*129},{"role":"admin"}):
        response=client.post("/api/v1/auth/login",json={"email":staff_user.email,"password":"Abc123",**({"password":"a"*257} if "password" in extra else extra)})
        assert response.status_code==422


def test_refresh_does_not_accept_json_token_as_cookie(client,staff_user):
    response=client.post("/api/v1/auth/refresh",json={"refresh_token":"legacy-jwt"})
    assert response.status_code==401


def test_me_without_session_denied_and_never_cached(client):
    response=client.get("/api/v1/auth/me")
    assert response.status_code==401 and response.headers["Cache-Control"]=="no-store"


def test_admin_registration_allows_multiple_accounts_without_setup_secret(client):
    payload = {"email": "first@example.com", "full_name": "First Admin", "password": PASSPHRASE}
    first = client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["user"]["role"] == "admin"

    client.cookies.clear()
    second = client.post("/api/v1/auth/register", json={**payload, "email": "second@example.com"})
    assert second.status_code == 201, second.text
    assert second.json()["user"]["role"] == "admin"

    client.cookies.clear()
    duplicate = client.post("/api/v1/auth/register", json=payload)
    assert duplicate.status_code == 409


def test_admin_registration_and_login_do_not_require_mfa_key(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "mfa_encryption_key", None)
    payload = {
        "email": "first@example.com",
        "full_name": "Admin",
        "password": PASSPHRASE,
    }
    created = client.post("/api/v1/auth/register", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["user"]["mfa_required"] is False
    client.cookies.clear()
    logged_in = client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert logged_in.status_code == 200, logged_in.text
    assert logged_in.json()["user"]["mfa_required"] is False


def test_existing_mfa_metadata_does_not_block_login_when_mfa_is_removed(client, admin_user, db_session, monkeypatch):
    admin_user.mfa_enabled_at = now()
    admin_user.mfa_secret = "legacy-encrypted-secret"
    db_session.commit()
    monkeypatch.setattr(get_settings(), "mfa_encryption_key", None)
    logged_in = client.post("/api/v1/auth/login", json={"email": admin_user.email, "password": "Abc123"})
    assert logged_in.status_code == 200, logged_in.text
    assert logged_in.json()["user"]["mfa_enabled"] is False
    assert logged_in.json()["user"]["mfa_required"] is False
    assert client.get("/api/v1/users").status_code == 200


def test_admin_registration_rejects_invalid_payload(client):
    response=client.post("/api/v1/auth/register",json={
        "email":"not-an-email","full_name":"Admin","password":PASSPHRASE,
    })
    assert response.status_code==422


def test_session_password_change_rejects_bad_current_password(client,staff_user):
    sign_in(client,staff_user)
    response=client.post("/api/v1/auth/password",json={"current_password":"wrong","new_password":PASSPHRASE})
    assert response.status_code==401
