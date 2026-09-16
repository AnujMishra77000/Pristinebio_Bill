import pytest
from fastapi.testclient import TestClient
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
    with TestClient(app) as test_client:
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
def auth_headers():
    def _headers(user):
        token = create_access_token(subject=str(user.id), role=user.role)
        return {"Authorization": f"Bearer {token}"}

    return _headers
