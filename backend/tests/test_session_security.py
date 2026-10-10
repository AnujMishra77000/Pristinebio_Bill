from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.user import AdminRegistrationCreate
import pyotp
from sqlalchemy import select, func
from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.authentication import AuthSession, AccountInvitation, RefreshCredential, SecurityAudit, MFARecoveryCode
from app.models.enums import UserRole
from app.models.user import User
from app.services.account_security import cipher, digest, now

PASSPHRASE="River!73"


def sign_in(client,user,password="Abc123"):
    response=client.post("/api/v1/auth/login",json={"email":user.email,"password":password})
    assert response.status_code==200,response.text
    return response


def cookie(client,kind):
    return client.cookies.get(get_settings().cookie_name(kind))


def enroll(client):
    response=client.post("/api/v1/auth/mfa/enroll",json={})
    assert response.status_code==200,response.text
    secret=response.json()["secret"]
    confirm=client.post("/api/v1/auth/mfa/confirm",json={"code":pyotp.TOTP(secret).now()})
    assert confirm.status_code==200,confirm.text
    return secret,confirm.json()["recovery_codes"]


@pytest.mark.parametrize("password", ["Qz7!xR", "Qz7!xR2@t9", "river café", "cafe\u0301 x"])
def test_new_passphrases_accept_six_to_ten_normalized_characters(password):
    import unicodedata
    value = AdminRegistrationCreate(email="new@example.com", full_name="New Admin", password=password)
    assert value.password == unicodedata.normalize("NFC", password)


@pytest.mark.parametrize("password", ["Qz7!x", "Qz7!xR2@t9V", "password", " " * 6, "a" * 6])
def test_new_passphrases_reject_short_common_blank_or_overlong(password):
    with pytest.raises(ValidationError):
        AdminRegistrationCreate(email="new@example.com", full_name="New Admin", password=password)


def test_existing_long_password_remains_valid_without_rewriting_hash(client,staff_user,db_session):
    from app.core.security import hash_password
    existing_password="quiet rivers drift beyond hills"
    staff_user.hashed_password=hash_password(existing_password)
    staff_user.password_policy_version=1
    db_session.commit()
    original=staff_user.hashed_password
    assert sign_in(client,staff_user,existing_password).status_code==200
    assert staff_user.hashed_password==original


def test_production_rejects_development_security_defaults():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_environment="production")


def test_public_registration_creates_an_admin_without_master_password(client):
    response = client.post("/api/v1/auth/register", json={"email":"new@example.com", "password":PASSPHRASE, "full_name":"Admin"})
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "admin"


def test_disabled_login_is_indistinguishable_from_invalid_login(client, staff_user, db_session):
    staff_user.is_active = False
    db_session.commit()
    disabled = client.post("/api/v1/auth/login", json={"email":staff_user.email,"password":"Abc123"})
    missing = client.post("/api/v1/auth/login", json={"email":"missing@example.com","password":"Abc123"})
    assert disabled.status_code == missing.status_code == 401
    assert disabled.json() == missing.json()


def test_cookie_only_login_no_tokens_in_json_and_bearer_no_longer_accepted(client,staff_user):
    response=sign_in(client,staff_user)
    assert set(response.json())=={"user"}
    assert cookie(client,"refresh") and cookie(client,"access")
    assert all("HttpOnly" in c and "SameSite=lax" in c for c in response.headers.get_list("set-cookie"))
    assert client.get("/api/v1/auth/me").json()["id"]==staff_user.id
    client.cookies.clear()
    token=create_access_token(str(staff_user.id),staff_user.role)
    assert client.get("/api/v1/auth/me",headers={"Authorization":f"Bearer {token}"}).status_code==401


def test_legacy_hash_unchanged_until_controlled_upgrade(client,staff_user,db_session):
    staff_user.password_policy_version=0
    original=staff_user.hashed_password
    db_session.commit()
    response=sign_in(client,staff_user)
    assert response.json()["user"]["password_change_required"]
    assert staff_user.hashed_password==original
    assert client.get("/api/v1/customers").json()["detail"]=="password_change_required"
    changed=client.post("/api/v1/auth/password",json={"current_password":"Abc123","new_password":PASSPHRASE})
    assert changed.status_code==200,changed.text
    assert not changed.json()["user"]["password_change_required"]
    assert staff_user.password_policy_version==1 and staff_user.hashed_password!=original
    assert client.get("/api/v1/customers").status_code==200


def test_admin_registration_is_available_after_other_accounts_exist(client, staff_user):
    response = client.post("/api/v1/auth/register", json={"email":"another@example.com", "password":PASSPHRASE, "full_name":"Another Admin"})
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "admin"


def test_login_throttle_is_persistent(client,staff_user,db_session):
    for _ in range(8):
        assert client.post("/api/v1/auth/login",json={"email":staff_user.email,"password":"wrong"}).status_code==401
    response=client.post("/api/v1/auth/login",json={"email":staff_user.email,"password":"Abc123"})
    assert response.status_code==429 and response.headers["Retry-After"]=="900"
    assert db_session.scalar(select(SecurityAudit).where(SecurityAudit.action=="authentication_throttled"))


def test_csrf_and_origin_are_required_even_for_login(client,staff_user):
    payload={"email":staff_user.email,"password":"Abc123"}
    assert client.raw_request("POST","/api/v1/auth/login",json=payload).status_code==403
    token=client.get("/api/v1/auth/csrf").json()["csrf_token"]
    assert client.raw_request("POST","/api/v1/auth/login",json=payload,headers={"Origin":"https://evil.example","X-CSRF-Token":token}).status_code==403
    assert client.raw_request("POST","/api/v1/auth/login",json=payload,headers={"Origin":get_settings().frontend_origin,"X-CSRF-Token":"forged"}).status_code==403
    assert client.post("/api/v1/auth/login",json=payload).status_code==200


def test_old_anonymous_csrf_cannot_be_used_after_login(client,staff_user):
    token=client.get("/api/v1/auth/csrf").json()["csrf_token"]
    sign_in(client,staff_user)
    assert client.raw_request("POST","/api/v1/auth/logout",headers={"Origin":get_settings().frontend_origin,"X-CSRF-Token":token}).status_code==403


def test_csrf_renewal_is_stable_for_tabs_in_the_same_session(client,staff_user):
    sign_in(client,staff_user)
    first=client.get("/api/v1/auth/csrf").json()["csrf_token"]
    second=client.get("/api/v1/auth/csrf").json()["csrf_token"]
    assert first==second


def replay_request(client,raw):
    headers={"Cookie":f"{get_settings().cookie_name('access')}={cookie(client,'access')}; {get_settings().cookie_name('refresh')}={raw}"}
    return client.post("/api/v1/auth/refresh",headers=headers)


def test_refresh_rotates_and_latest_predecessor_grace_returns_same_successor(client,staff_user,db_session):
    sign_in(client,staff_user)
    old=cookie(client,"refresh")
    assert client.post("/api/v1/auth/refresh").status_code==200
    successor=cookie(client,"refresh")
    assert successor!=old
    assert replay_request(client,old).status_code==200
    assert cookie(client,"refresh")==successor
    assert db_session.scalar(select(func.count()).select_from(RefreshCredential))==2


def test_refresh_replay_after_grace_revokes_session(client,staff_user,db_session):
    sign_in(client,staff_user)
    old=cookie(client,"refresh")
    assert client.post("/api/v1/auth/refresh").status_code==200
    credential=db_session.get(RefreshCredential,digest(old))
    credential.consumed_at=now()-timedelta(seconds=20)
    db_session.commit()
    assert replay_request(client,old).status_code==401
    assert client.get("/api/v1/auth/me").status_code==401
    assert db_session.scalar(select(SecurityAudit).where(SecurityAudit.action=="refresh_replay_revoked"))


def test_older_generation_replay_revokes_even_within_grace(client,staff_user):
    sign_in(client,staff_user)
    old=cookie(client,"refresh")
    client.post("/api/v1/auth/refresh")
    client.post("/api/v1/auth/refresh")
    assert replay_request(client,old).status_code==401


@pytest.mark.parametrize("expired",["absolute","idle"])
def test_expiration_is_enforced_on_backend(client,staff_user,db_session,expired):
    sign_in(client,staff_user)
    session=db_session.scalar(select(AuthSession))
    if expired=="absolute":
        session.expires_at=now()-timedelta(seconds=1)
    else:
        session.last_seen_at=now()-timedelta(minutes=get_settings().session_idle_minutes+1)
    db_session.commit()
    assert client.get("/api/v1/auth/me").status_code==401
    assert client.post("/api/v1/auth/refresh").status_code==401


def test_logout_revokes_tokens_and_clears_cookies(client,staff_user,db_session):
    sign_in(client,staff_user)
    access=cookie(client,"access")
    assert client.post("/api/v1/auth/logout").status_code==200
    assert not cookie(client,"access") and not cookie(client,"refresh")
    assert client.get("/api/v1/auth/me",headers={"Cookie":f"{get_settings().cookie_name('access')}={access}"}).status_code==401
    assert db_session.scalar(select(AuthSession)).revoked_at


def test_disabled_account_revokes_effective_access_immediately(client,staff_user,db_session):
    sign_in(client,staff_user)
    staff_user.is_active=False
    db_session.commit()
    assert client.get("/api/v1/auth/me").status_code==401
    assert client.post("/api/v1/auth/refresh").status_code==401
