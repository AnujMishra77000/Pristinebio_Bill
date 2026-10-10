from datetime import timedelta
import pyotp
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, func
from app.core.config import get_settings, Settings
from app.models.authentication import AccountInvitation, SecurityAudit, MFARecoveryCode, AuthSession
from app.models.user import User
from app.services.account_security import cipher, now
from test_session_security import sign_in, enroll, PASSPHRASE


def test_invitation_single_use_email_bound_and_hashed(client,admin_user,branch,db_session,auth_headers):
    response=client.post("/api/v1/auth/invitations",headers=auth_headers(admin_user),json={"email":"invited@example.com","role":"staff","branch_ids":[branch.id]})
    assert response.status_code==201,response.text
    invitation=response.json()
    assert db_session.get(AccountInvitation,invitation["id"]).token_hash!=invitation["token"]
    assert "token" not in client.get("/api/v1/auth/invitations",headers=auth_headers(admin_user)).json()[0]
    client.cookies.clear()
    payload={"token":invitation["token"],"email":"attacker@example.com","full_name":"Invited Staff","password":PASSPHRASE}
    accepted=client.post("/api/v1/auth/invitations/accept",json=payload)
    assert accepted.status_code==201,accepted.text
    assert accepted.json()["user"]["email"]=="invited@example.com"
    assert client.post("/api/v1/auth/invitations/accept",json=payload).status_code==401
    assert db_session.scalar(select(func.count()).select_from(User).where(User.email=="invited@example.com"))==1


def test_invitation_revocation_and_expiration(client,admin_user,branch,db_session,auth_headers):
    headers=auth_headers(admin_user)
    for revoked in (True,False):
        invite=client.post("/api/v1/auth/invitations",headers=headers,json={"email":f"new{revoked}@example.com","role":"manager","branch_ids":[branch.id]}).json()
        if revoked:
            assert client.delete(f"/api/v1/auth/invitations/{invite['id']}",headers=headers).status_code==200
        else:
            db_session.get(AccountInvitation,invite["id"]).expires_at=now()-timedelta(seconds=1)
            db_session.commit()
        assert client.post("/api/v1/auth/invitations/accept",json={"token":invite["token"],"full_name":"New User","password":PASSPHRASE}).status_code==401


@pytest.mark.parametrize("fixture",["staff_user","manager_user"])
def test_nonadmins_cannot_provision_or_edit_sensitive_defaults(client,request,fixture,branch,auth_headers):
    headers=auth_headers(request.getfixturevalue(fixture))
    assert client.post("/api/v1/auth/invitations",headers=headers,json={"email":"new@example.com","role":"admin"}).status_code==403
    assert client.put("/api/v1/companies/profile",headers=headers,json={}).status_code==403
    assert client.post("/api/v1/bank-accounts",headers=headers,json={}).status_code==403
    assert client.patch(f"/api/v1/branches/{branch.id}",headers=headers,json={"gstin":"29AAAAA0000A1Z5"}).status_code==403


@pytest.mark.parametrize("patch",[{"is_active":False},{"role":"staff"}])
def test_last_active_admin_cannot_be_removed(client,admin_user,auth_headers,patch):
    response=client.patch(f"/api/v1/users/{admin_user.id}",headers=auth_headers(admin_user),json=patch)
    assert response.status_code==409 and "last active" in response.json()["detail"]


def test_account_changes_are_audited_and_sessions_revoked(client,admin_user,staff_user,db_session,auth_headers):
    staff_headers=auth_headers(staff_user)
    response=client.patch(f"/api/v1/users/{staff_user.id}",headers=auth_headers(admin_user),json={"is_active":False})
    assert response.status_code==200,response.text
    assert client.get("/api/v1/auth/me",headers=staff_headers).status_code==401
    entry=db_session.scalar(select(SecurityAudit).where(SecurityAudit.action=="account_updated"))
    assert entry.actor_id==admin_user.id and entry.created_at
    assert entry.before["is_active"] is True and entry.after["is_active"] is False
    assert "hashed_password" not in str(entry.before)


def test_privileged_mfa_enrollment_and_recovery_full_lifecycle(client,admin_user,db_session):
    response=sign_in(client,admin_user)
    assert response.json()["user"]["mfa_required"] and not response.json()["user"]["mfa_verified"]
    assert client.get("/api/v1/users").json()["detail"]=="mfa_enrollment_required"
    secret,codes=enroll(client)
    assert len(codes)==10 and len(set(codes))==10
    assert admin_user.mfa_secret!=secret
    assert db_session.scalar(select(func.count()).select_from(MFARecoveryCode))==10
    assert client.get("/api/v1/users").status_code==200
    client.post("/api/v1/auth/logout")
    sign_in(client,admin_user)
    assert client.get("/api/v1/users").json()["detail"]=="mfa_verification_required"
    assert client.post("/api/v1/auth/mfa/verify",json={"code":pyotp.TOTP(secret).now()}).status_code==401
    recovered=client.post("/api/v1/auth/mfa/recover",json={"code":codes[0]})
    assert recovered.status_code==200,recovered.text
    assert not recovered.json()["user"]["mfa_enabled"] and recovered.json()["user"]["mfa_required"]
    assert client.get("/api/v1/users").status_code==403
    assert client.post("/api/v1/auth/mfa/recover",json={"code":codes[0]}).status_code==401
    new_secret,new_codes=enroll(client)
    assert new_secret!=secret and new_codes!=codes
    assert client.get("/api/v1/users").status_code==200


def test_mfa_pending_enrollment_expiry(client,admin_user,db_session):
    sign_in(client,admin_user)
    data=client.post("/api/v1/auth/mfa/enroll",json={}).json()
    admin_user.mfa_pending_expires_at=now()-timedelta(seconds=1)
    db_session.commit()
    assert client.post("/api/v1/auth/mfa/confirm",json={"code":pyotp.TOTP(data["secret"]).now()}).status_code==422


def test_mfa_recovery_replacement_and_administrative_reset(client,admin_user,manager_user,auth_headers,db_session):
    headers=auth_headers(admin_user)
    secret=cipher().decrypt(admin_user.mfa_secret.encode()).decode()
    replaced=client.post("/api/v1/auth/mfa/recovery-codes",headers=headers,json={"current_password":"Abc123","code":pyotp.TOTP(secret).now()})
    assert replaced.status_code==200,replaced.text
    assert len(replaced.json()["recovery_codes"])==10
    admin_user.mfa_last_step-=1
    db_session.commit()
    assert client.post(f"/api/v1/users/{admin_user.id}/mfa-reset",headers=headers,json={"current_password":"Abc123","code":pyotp.TOTP(secret).now(),"reason":"Lost phone"}).status_code==403
    auth_headers(manager_user)
    reset=client.post(f"/api/v1/users/{manager_user.id}/mfa-reset",headers=headers,json={"current_password":"Abc123","code":pyotp.TOTP(secret).now(),"reason":"Verified lost authenticator"})
    assert reset.status_code==200,reset.text
    assert manager_user.mfa_secret is None and manager_user.mfa_reenrollment_required
    entry=db_session.scalar(select(SecurityAudit).where(SecurityAudit.action=="mfa_administrative_reset"))
    assert entry.actor_id==admin_user.id and entry.after["reason"]=="Verified lost authenticator"


def test_existing_authenticator_cannot_be_replaced_without_reauthentication(client,admin_user,auth_headers):
    assert client.post("/api/v1/auth/mfa/enroll",headers=auth_headers(admin_user),json={}).status_code==401


def test_secure_production_configuration_and_host_cookies(client,staff_user,monkeypatch):
    from secrets import token_urlsafe
    settings=Settings(_env_file=None,app_environment="production",jwt_secret_key=token_urlsafe(48),mfa_encryption_key=Fernet.generate_key().decode(),cookie_secure=True,frontend_origin="https://billing.example.org",database_url="postgresql+psycopg://billing:a-long-private-db-passphrase@db/billing")
    assert settings.cookie_name("access")=="__Host-billing_access"
    monkeypatch.setattr(get_settings(),"cookie_secure",True)
    import httpx
    client.base_url=httpx.URL("https://testserver")
    response=sign_in(client,staff_user)
    assert all("Secure" in c and "Path=/" in c and "Domain=" not in c for c in response.headers.get_list("set-cookie"))


def test_explicit_null_account_patch_and_password_setter_are_rejected(client,admin_user,auth_headers):
    headers=auth_headers(admin_user)
    assert client.patch(f"/api/v1/users/{admin_user.id}",headers=headers,json={"role":None}).status_code==422
    assert client.patch(f"/api/v1/users/{admin_user.id}",headers=headers,json={"password":PASSPHRASE}).status_code==422


def test_current_and_all_sessions_can_be_revoked(client,staff_user,db_session):
    sign_in(client,staff_user)
    first=db_session.scalar(select(AuthSession)).id
    sign_in(client,staff_user)
    sessions=client.get("/api/v1/auth/sessions").json()
    assert len(sessions)==2 and sum(s["current"] for s in sessions)==1
    assert client.delete(f"/api/v1/auth/sessions/{first}").status_code==200
    assert client.post("/api/v1/auth/logout-all").status_code==200
    assert client.get("/api/v1/auth/me").status_code==401


def test_normal_mfa_login_and_code_replay(client,admin_user,auth_headers,db_session):
    auth_headers(admin_user)
    secret=cipher().decrypt(admin_user.mfa_secret.encode()).decode()
    sign_in(client,admin_user)
    verified=client.post("/api/v1/auth/mfa/verify",json={"code":pyotp.TOTP(secret).now()})
    assert verified.status_code==200,verified.text
    assert verified.json()["user"]["mfa_verified"]
    assert client.get("/api/v1/users").status_code==200
    assert client.post("/api/v1/auth/mfa/verify",json={"code":pyotp.TOTP(secret).now()}).status_code==401


def test_sensitive_profile_and_bank_edits_capture_before_after(client,admin_user,branch,auth_headers,db_session):
    from test_seller_profile import _profile_payload
    from test_remaining_masters import bank_account_payload
    headers=auth_headers(admin_user)
    original_gstin=branch.gstin
    updated=client.put("/api/v1/companies/profile",headers=headers,json=_profile_payload())
    assert updated.status_code==200,updated.text
    event=db_session.scalar(select(SecurityAudit).where(SecurityAudit.action=="seller_profile_updated"))
    assert event.actor_id==admin_user.id
    assert event.before["seller_profile"]["gstin"]==original_gstin
    assert event.after["seller_profile"]["bank_account_number"]=="777705889826"
    created=client.post("/api/v1/bank-accounts",headers=headers,json=bank_account_payload(branch.id))
    assert created.status_code==201
    assert client.patch(f"/api/v1/bank-accounts/{created.json()['id']}",headers=headers,json={"account_number":"999999999999"}).status_code==200
    bank=db_session.scalar(select(SecurityAudit).where(SecurityAudit.action=="bank_account_updated"))
    assert bank.before["account_number"]=="12345678901" and bank.after["account_number"]=="999999999999"


def test_password_change_revokes_other_sessions(client,staff_user,auth_headers,db_session):
    old_headers=auth_headers(staff_user)
    sign_in(client,staff_user)
    changed=client.post("/api/v1/auth/password",json={"current_password":"Abc123","new_password":PASSPHRASE})
    assert changed.status_code==200
    assert client.get("/api/v1/auth/me",headers=old_headers).status_code==401
    assert client.get("/api/v1/auth/me").status_code==200


def test_invitation_acceptance_rejects_privilege_injection(client):
    response=client.post("/api/v1/auth/invitations/accept",json={"token":"a"*64,"full_name":"User","password":PASSPHRASE,"role":"admin","branch_ids":[1]})
    assert response.status_code==422


def test_recovery_code_replacement_invalidates_previous_codes(client,admin_user,auth_headers,db_session):
    headers=auth_headers(admin_user)
    secret=cipher().decrypt(admin_user.mfa_secret.encode()).decode()
    previous=client.post("/api/v1/auth/mfa/recovery-codes",headers=headers,json={"current_password":"Abc123","code":pyotp.TOTP(secret).now()}).json()["recovery_codes"]
    admin_user.mfa_last_step-=1
    db_session.commit()
    next_codes=client.post("/api/v1/auth/mfa/recovery-codes",headers=headers,json={"current_password":"Abc123","code":pyotp.TOTP(secret).now()}).json()["recovery_codes"]
    assert next_codes!=previous
    sign_in(client,admin_user)
    assert client.post("/api/v1/auth/mfa/recover",json={"code":previous[0]}).status_code==401


def test_decomposed_unicode_passphrase_roundtrip_login_and_reauthentication(client,staff_user,admin_user,auth_headers,db_session):
    raw=("e\u0301x"*4)+"yz"
    assert len(raw)==14
    sign_in(client,staff_user)
    changed=client.post("/api/v1/auth/password",json={"current_password":"Abc123","new_password":raw})
    assert changed.status_code==200,changed.text
    client.post("/api/v1/auth/logout")
    assert sign_in(client,staff_user,raw).status_code==200
    changed=client.post("/api/v1/auth/password",json={"current_password":raw,"new_password":PASSPHRASE})
    assert changed.status_code==200,changed.text
    # The same decomposed input is valid for privileged MFA reauthentication.
    from app.core.security import hash_password, validate_passphrase
    admin_user.hashed_password=hash_password(validate_passphrase(raw))
    db_session.commit()
    headers=auth_headers(admin_user)
    secret=cipher().decrypt(admin_user.mfa_secret.encode()).decode()
    assert client.post("/api/v1/auth/mfa/recovery-codes",headers=headers,json={"current_password":raw,"code":pyotp.TOTP(secret).now()}).status_code==200


def test_validation_errors_do_not_echo_passwords(client):
    secret="too-short-secret"
    response=client.post("/api/v1/auth/register",json={"email":"not-email","full_name":"Name","password":secret})
    assert response.status_code==422 and secret not in response.text
