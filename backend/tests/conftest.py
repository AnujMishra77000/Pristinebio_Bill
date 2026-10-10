import pytest
from fastapi.testclient import TestClient
from fastapi import Request, Response
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models
from app.core.security import create_access_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models.company import Branch, Company
from app.models.enums import UserRole
from app.models.user import User, UserBranchAssignment
from app.core.config import get_settings
from app.core.csrf import issue_csrf
from app.services.account_security import cipher, new_session, now


@pytest.fixture(autouse=True)
def security_config(monkeypatch):
    monkeypatch.setattr(get_settings(), "mfa_encryption_key", Fernet.generate_key().decode())


class SecurityTestClient(TestClient):
    """Ordinary test requests use real CSRF; raw_request tests hostile requests."""
    def raw_request(self, method, url, **kwargs):
        return super().request(method,url,**kwargs)

    def request(self, method, url, **kwargs):
        if method.upper() not in {"GET","HEAD","OPTIONS"}:
            headers=dict(kwargs.pop("headers",{}) or {})
            if "X-CSRF-Token" not in headers:
                csrf=super().request("GET","/api/v1/auth/csrf",headers=headers)
                headers["X-CSRF-Token"]=csrf.json()["csrf_token"]
                if "Cookie" in headers:
                    headers["Cookie"] += f"; {get_settings().cookie_name('csrf')}={headers['X-CSRF-Token']}"
            headers.setdefault("Origin",get_settings().frontend_origin.rstrip("/"))
            kwargs["headers"]=headers
        return super().request(method,url,**kwargs)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with SecurityTestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def company(db_session: Session):
    value = Company(
        legal_name="Pristine Bio Chemicals Private Limited",
        trade_name="Pristine Bio",
        pan="AAAAA0000A",
        registered_address="1 Billing Street",
    )
    db_session.add(value)
    db_session.commit()
    db_session.refresh(value)
    return value


def _create_branch(db_session: Session, company: Company, name: str, gstin: str):
    value = Branch(
        company_id=company.id,
        name=name,
        gstin=gstin,
        address_line1=f"{name} Address",
        city="Hyderabad",
        state="Telangana",
        state_code="36",
        postal_code="500001",
    )
    db_session.add(value)
    db_session.commit()
    db_session.refresh(value)
    return value


@pytest.fixture()
def branch(db_session: Session, company: Company):
    return _create_branch(db_session, company, "Hyderabad Branch", "36AAAAA0000A1Z5")


@pytest.fixture()
def other_branch(db_session: Session, company: Company):
    return _create_branch(db_session, company, "Bengaluru Branch", "29AAAAA0000A1Z5")


def _create_user(
    db_session: Session,
    role: UserRole,
    email: str,
    full_name: str,
    branch: Branch | None = None,
):
    value = User(
        email=email,
        full_name=full_name,
        role=role,
        hashed_password=hash_password("Abc123"),
        password_policy_version=1,
    )
    db_session.add(value)
    db_session.commit()
    db_session.refresh(value)

    if branch is not None:
        db_session.add(UserBranchAssignment(user_id=value.id, branch_id=branch.id))
        db_session.commit()
        db_session.refresh(value)

    return value


@pytest.fixture()
def admin_user(db_session: Session):
    return _create_user(
        db_session, UserRole.ADMIN, "admin@example.com", "Admin User"
    )


@pytest.fixture()
def manager_user(db_session: Session, branch: Branch):
    return _create_user(
        db_session,
        UserRole.MANAGER,
        "manager@example.com",
        "Manager User",
        branch,
    )


@pytest.fixture()
def staff_user(db_session: Session, branch: Branch):
    return _create_user(
        db_session, UserRole.STAFF, "staff@example.com", "Staff User", branch
    )


@pytest.fixture()
def auth_headers(db_session):
    def _headers(user):
        if user.role in {UserRole.ADMIN,UserRole.MANAGER} and not user.mfa_enabled_at:
            user.mfa_enabled_at=now()
            user.mfa_secret=cipher().encrypt(b"JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP").decode()
        response=Response()
        session=new_session(db_session,user,response,mfa_verified=True)
        db_session.commit()
        cookie="; ".join(value.split(";",1)[0] for value in response.headers.getlist("set-cookie"))
        request=Request({"type":"http","headers":[(b"cookie",cookie.encode())]})
        csrf=issue_csrf(request)
        return {"Cookie":cookie+f"; {get_settings().cookie_name('csrf')}={csrf}","X-CSRF-Token":csrf,"Origin":get_settings().frontend_origin.rstrip("/")}

    return _headers
