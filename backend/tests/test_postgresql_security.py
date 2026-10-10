"""Real races, isolated schemas only. Never run against the client database.

Set TEST_SECURITY_DATABASE_URL to a disposable database named billing_security_test.
"""
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import Request, Response
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.csrf import issue_csrf
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models.authentication import AuthSession, RefreshCredential, SecurityAudit
from app.models.company import Company, Branch
from app.models.enums import UserRole
from app.models.user import User
from app.services.account_security import cipher, digest, new_session, now, rotate_refresh
from conftest import SecurityTestClient


@pytest.fixture()
def pg_sessions():
    url=os.environ.get("TEST_SECURITY_DATABASE_URL")
    if not url:
        pytest.skip("TEST_SECURITY_DATABASE_URL not configured (disposable PostgreSQL required)")
    if make_url(url).database!="billing_security_test":
        pytest.fail("Refusing non-disposable database; use billing_security_test")
    schema="security_"+uuid4().hex
    control=create_engine(url)
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine=create_engine(url,connect_args={"options":f"-csearch_path={schema}"})
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,autoflush=False)
    try:
        yield factory
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def seed(factory,admins=1):
    values=[]
    with factory() as db:
        company=Company(legal_name="Security Test Company")
        db.add(company);db.flush()
        branch=Branch(company_id=company.id,name="Security Seller",gstin="36AAAAA0000A1Z5",address_line1="Address",city="Hyderabad",state="Telangana",state_code="36",postal_code="500001")
        db.add(branch);db.flush()
        for i in range(admins):
            user=User(email=f"admin{i}@example.com",full_name=f"Admin {i}",role=UserRole.ADMIN,hashed_password=hash_password("quiet rivers drift beyond hills"),password_policy_version=1,mfa_secret=cipher().encrypt(b"JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP").decode(),mfa_enabled_at=now())
            db.add(user);db.flush()
            response=Response()
            session=new_session(db,user,response,mfa_verified=True)
            cookie="; ".join(v.split(";",1)[0] for v in response.headers.getlist("set-cookie"))
            csrf=issue_csrf(Request({"type":"http","headers":[(b"cookie",cookie.encode())]}))
            values.append((user.id,session.id,{"Cookie":cookie+f"; {get_settings().cookie_name('csrf')}={csrf}","Origin":get_settings().frontend_origin,"X-CSRF-Token":csrf}))
        db.commit()
        return values,branch.id


def test_concurrent_refresh_returns_one_successor(pg_sessions):
    values,_=seed(pg_sessions)
    user_id,session_id,headers=values[0]
    raw=headers["Cookie"].split("billing_refresh=",1)[1].split(";",1)[0]
    barrier=Barrier(2)
    def refresh():
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            response=Response()
            rotate_refresh(db,raw,response)
            return [v for v in response.headers.getlist("set-cookie") if "billing_refresh=" in v][0]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _:refresh(),range(2)))
    assert results[0]==results[1]
    with pg_sessions() as db:
        assert db.scalar(select(func.count()).select_from(RefreshCredential))==2
        assert not db.get(AuthSession,session_id).revoked_at


def pg_clients(factory):
    def override_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db]=override_db
    return SecurityTestClient(app)


def test_concurrent_last_admin_demotions_keep_one_active_admin(pg_sessions):
    values,branch_id=seed(pg_sessions,admins=2)
    barrier=Barrier(2)
    client=pg_clients(pg_sessions)
    def demote(value):
        uid,_,headers=value
        barrier.wait(timeout=10)
        return client.patch(f"/api/v1/users/{uid}",headers=headers,json={"role":"manager","branch_ids":[branch_id]}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses=list(executor.map(demote,values))
    assert sorted(statuses)==[200,409]
    with pg_sessions() as db:
        assert db.scalar(select(func.count()).select_from(User).where(User.role==UserRole.ADMIN,User.is_active.is_(True)))==1
    client.close()


def test_concurrent_invitation_acceptance_creates_one_account(pg_sessions):
    values,branch_id=seed(pg_sessions)
    client=pg_clients(pg_sessions)
    created=client.post("/api/v1/auth/invitations",headers=values[0][2],json={"email":"new@example.com","role":"staff","branch_ids":[branch_id]})
    assert created.status_code==201,created.text
    token=created.json()["token"]
    barrier=Barrier(2)
    def accept(_):
        # Independent browser cookie jars, sharing only the intended invite.
        with SecurityTestClient(app) as browser:
            barrier.wait(timeout=10)
            return browser.post("/api/v1/auth/invitations/accept",json={"token":token,"full_name":"New Staff","password":"River!73"}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses=list(executor.map(accept,range(2)))
    assert sorted(statuses)==[201,401]
    with pg_sessions() as db:
        assert db.scalar(select(func.count()).select_from(User).where(User.email=="new@example.com"))==1
    client.close()


def test_security_migration_preserves_existing_hash_and_closes_setup(pg_sessions):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    with pg_sessions() as db:
        # Dedicated isolated schema starts with current metadata. Remove only
        # security objects to recreate the exact pre-security user columns.
        for table in ("security_audit_logs","mfa_recovery_codes","account_invitations","auth_refresh_credentials","auth_sessions","auth_throttles","admin_setup_state"):
            db.execute(text(f'DROP TABLE "{table}"'))
        for column in ("password_policy_version","mfa_secret","mfa_pending_secret","mfa_pending_expires_at","mfa_enabled_at","mfa_last_step","mfa_reenrollment_required"):
            db.execute(text(f'ALTER TABLE users DROP COLUMN "{column}"'))
        hashed=hash_password("Abc123")
        db.execute(text("INSERT INTO users(email,full_name,role,hashed_password,is_active) VALUES ('legacy@example.com','Legacy Admin','admin',:hash,true)"),{"hash":hashed})
        path=Path(__file__).parents[1]/"alembic/versions/20260916_0009_session_security.py"
        spec=importlib.util.spec_from_file_location("security_migration",path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        context=MigrationContext.configure(db.connection())
        with Operations.context(context):
            module.upgrade()
        row=db.execute(text("SELECT hashed_password,password_policy_version FROM users WHERE email='legacy@example.com'")).one()
        assert row.hashed_password==hashed and row.password_policy_version==0
        assert db.scalar(text("SELECT completed_at FROM admin_setup_state WHERE id=1")) is not None
        db.commit()


def test_revoked_cached_mfa_challenge_cannot_issue_new_session(pg_sessions):
    from app.api.v1.auth import verify_mfa
    from app.schemas.auth import MFACode
    from fastapi import HTTPException
    import pyotp
    values,_=seed(pg_sessions)
    uid,sid,_=values[0]
    with pg_sessions() as request_db:
        user=request_db.get(User,uid)
        source=request_db.get(AuthSession,sid)
        request=Request({"type":"http","headers":[],"client":("127.0.0.1",1234)})
        request.state.auth_session=source
        with pg_sessions() as revoke_db:
            revoke_db.get(AuthSession,sid).revoked_at=now()
            revoke_db.commit()
        secret=cipher().decrypt(user.mfa_secret.encode()).decode()
        with pytest.raises(HTTPException) as denied:
            verify_mfa(MFACode(code=pyotp.TOTP(secret).now()),request,Response(),request_db,user)
        assert denied.value.status_code==401
    with pg_sessions() as db:
        assert db.scalar(select(func.count()).select_from(AuthSession))==1


def test_demoted_cached_actor_cannot_reset_mfa(pg_sessions):
    from app.api.v1.users import administrative_mfa_reset
    from app.schemas.auth import MFAReset
    from fastapi import HTTPException
    import pyotp
    values,_=seed(pg_sessions,admins=2)
    uid,sid,_=values[0]
    target_id=values[1][0]
    with pg_sessions() as request_db:
        actor=request_db.get(User,uid)
        source=request_db.get(AuthSession,sid)
        secret=cipher().decrypt(actor.mfa_secret.encode()).decode()
        request=Request({"type":"http","headers":[],"client":("127.0.0.1",1234)})
        request.state.auth_session=source
        with pg_sessions() as change_db:
            change_db.get(User,uid).role=UserRole.STAFF
            change_db.get(AuthSession,sid).revoked_at=now()
            change_db.commit()
        with pytest.raises(HTTPException) as denied:
            administrative_mfa_reset(target_id,MFAReset(current_password="quiet rivers drift beyond hills",code=pyotp.TOTP(secret).now(),reason="Lost phone"),request,request_db,actor)
        assert denied.value.status_code in (401,403)
    with pg_sessions() as db:
        assert db.get(User,target_id).mfa_enabled_at is not None


def test_concurrent_password_change_and_logout_finish_without_deadlock(pg_sessions):
    values,_=seed(pg_sessions)
    uid,sid,headers=values[0]
    client=pg_clients(pg_sessions)
    barrier=Barrier(2)
    def change(_):
        barrier.wait(timeout=10)
        return client.post("/api/v1/auth/password",headers=headers,json={"current_password":"quiet rivers drift beyond hills","new_password":"Other!74"}).status_code
    def logout(_):
        barrier.wait(timeout=10)
        return client.post("/api/v1/auth/logout",headers=headers).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        a=executor.submit(change,0);b=executor.submit(logout,0)
        assert a.result(timeout=10) in (200,401)
        assert b.result(timeout=10)==200
    client.close()


def test_concurrent_sensitive_patch_audit_uses_actual_preceding_state(pg_sessions):
    from test_remaining_masters import bank_account_payload
    values,branch_id=seed(pg_sessions)
    headers=values[0][2]
    client=pg_clients(pg_sessions)
    created=client.post("/api/v1/bank-accounts",headers=headers,json=bank_account_payload(branch_id))
    assert created.status_code==201,created.text
    account_id=created.json()["id"]
    barrier=Barrier(2)
    def patch(payload):
        barrier.wait(timeout=10)
        return client.patch(f"/api/v1/bank-accounts/{account_id}",headers=headers,json=payload).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses=list(executor.map(patch,[{"account_number":"888888888888"},{"bank_name":"Updated secure bank"}]))
    assert statuses==[200,200]
    with pg_sessions() as db:
        events=list(db.scalars(select(SecurityAudit).where(SecurityAudit.action=="bank_account_updated").order_by(SecurityAudit.id)))
        assert len(events)==2
        for field in ("bank_name","account_number","is_default"):
            assert events[1].before[field]==events[0].after[field]
        assert events[1].after["bank_name"]=="Updated secure bank"
        assert events[1].after["account_number"]=="888888888888"
    client.close()
