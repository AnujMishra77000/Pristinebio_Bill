# Phase 1B Authentication, Permissions, and Master Records Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build secure authentication, role and branch permissions, and the master-record foundation for Phase 1 billing work.

**Architecture:** The backend will add SQLAlchemy models, Pydantic schemas, JWT/Argon2 security helpers, auth dependencies, and protected `/api/v1` routers. The frontend will keep the existing Next.js App Router shell and add client-side login plus basic management screens backed by the new APIs.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL `Numeric`, Argon2 via `pwdlib`, JWT via `PyJWT`, Next.js App Router, React, TypeScript, Tailwind CSS.

**Spec:** `docs/superpowers/specs/2026-08-25-phase-1b-auth-master-records-design.md`

## Global Constraints

- Work only on Phase 1B: authentication, permissions, and master records.
- Read `AGENTS.md`, `docs/BILLING_CONTEXT.md`, and `docs/PROJECT_STATUS.md` before making changes.
- Do not scan `.git`, `node_modules`, `.next`, `dist`, coverage directories, or virtual environments.
- Preserve existing working code and avoid unrelated refactors.
- Use `Decimal` for money, rates, and quantity-ready values; never use binary floating-point types for billing calculations.
- Keep application API routes under `/api/v1`; keep the existing unversioned `/health` endpoint unchanged.
- Add targeted tests for changed behavior.
- Run targeted tests during development and the full backend test suite at phase completion.
- Do not implement invoice calculations, PDF generation, GST APIs, inventory movements, batch/lot tracking, Celery workflows, or Android-specific behavior.
- Update `docs/PROJECT_STATUS.md` before stopping.

---

## File Structure

Backend files:

- Modify `backend/requirements.txt`: add `pwdlib[argon2]`, `PyJWT`, and `email-validator`.
- Modify `backend/app/core/config.py`: add JWT and admin bootstrap settings.
- Create `backend/app/core/security.py`: password hashing and JWT helpers.
- Create `backend/app/models/__init__.py`: import all Phase 1B models for Alembic metadata.
- Create `backend/app/models/enums.py`: `UserRole`.
- Create `backend/app/models/mixins.py`: timestamp mixin.
- Create `backend/app/models/user.py`: user and branch-assignment models.
- Create `backend/app/models/company.py`: company and branch models.
- Create `backend/app/models/master_records.py`: customer, product, bank account, transporter, and terms models.
- Modify `backend/alembic/env.py`: import `app.models` before reading `Base.metadata`.
- Create `backend/alembic/versions/20260825_0001_phase_1b_auth_master_records.py`: schema migration.
- Create `backend/app/schemas/common.py`: shared schema config and address schemas.
- Create `backend/app/schemas/auth.py`: token and login schemas.
- Create `backend/app/schemas/user.py`: user create/update/read schemas.
- Create `backend/app/schemas/company.py`: company schemas.
- Create `backend/app/schemas/branch.py`: branch schemas.
- Create `backend/app/schemas/master_records.py`: customer, product, bank account, transporter, and terms schemas.
- Create `backend/app/api/dependencies.py`: current-user, role, and branch-authorization dependencies.
- Create `backend/app/api/v1/auth.py`: login, refresh, me, and guarded admin bootstrap routes.
- Create `backend/app/api/v1/users.py`: Admin user-management routes.
- Create `backend/app/api/v1/companies.py`: company routes.
- Create `backend/app/api/v1/branches.py`: branch routes.
- Create `backend/app/api/v1/customers.py`: customer routes.
- Create `backend/app/api/v1/products.py`: product routes.
- Create `backend/app/api/v1/bank_accounts.py`: bank-account routes.
- Create `backend/app/api/v1/transporters.py`: transporter routes.
- Create `backend/app/api/v1/terms.py`: terms-and-conditions routes.
- Modify `backend/app/api/v1/router.py`: include all new routers.
- Modify `.env.example`: add JWT and admin bootstrap variables.
- Create `backend/tests/conftest.py`: isolated database and authenticated-client helpers.
- Create `backend/tests/test_security.py`: password and token helper tests.
- Create `backend/tests/test_auth.py`: auth route tests.
- Create `backend/tests/test_permissions.py`: role and branch authorization tests.
- Create `backend/tests/test_master_records.py`: validation and branch-scoped master tests.

Frontend files:

- Create `frontend/app/lib/types.ts`: API response and master-record types.
- Create `frontend/app/lib/api.ts`: token storage and typed API requests.
- Create `frontend/app/components/AppShell.tsx`: shared responsive shell and navigation.
- Create `frontend/app/components/AuthGate.tsx`: lightweight login-required wrapper.
- Create `frontend/app/components/MasterDataPage.tsx`: reusable table/form screen component.
- Create `frontend/app/login/page.tsx`: login form.
- Modify `frontend/app/page.tsx`: dashboard using shared shell.
- Create `frontend/app/branches/page.tsx`.
- Create `frontend/app/customers/page.tsx`.
- Create `frontend/app/products/page.tsx`.
- Create `frontend/app/bank-accounts/page.tsx`.
- Create `frontend/app/transporters/page.tsx`.
- Create `frontend/app/terms/page.tsx`.
- Create `frontend/app/settings/page.tsx`.

---

### Task 1: Backend Security Helpers

**Files:**

- Modify: `backend/requirements.txt`
- Modify: `backend/app/core/config.py`
- Create: `backend/app/core/security.py`
- Create: `backend/app/models/enums.py`
- Test: `backend/tests/test_security.py`

**Interfaces:**

- Produces: `UserRole`, `hash_password(password: str) -> str`, `verify_password(plain_password: str, hashed_password: str) -> bool`, `create_access_token(subject: str, role: UserRole) -> str`, `create_refresh_token(subject: str, role: UserRole) -> str`, `decode_token(token: str, expected_type: str) -> dict[str, Any]`.
- Consumes: `Settings.jwt_secret_key`, `Settings.jwt_algorithm`, `Settings.access_token_expire_minutes`, `Settings.refresh_token_expire_days`.

- [ ] **Step 1: Write the failing security tests**

Create `backend/tests/test_security.py`:

```python
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.enums import UserRole


def test_argon2_password_hash_verifies_correct_password():
    hashed = hash_password("Correct-Horse-Battery-937")

    assert hashed != "Correct-Horse-Battery-937"
    assert verify_password("Correct-Horse-Battery-937", hashed)
    assert not verify_password("incorrect-password", hashed)


def test_access_and_refresh_tokens_have_distinct_token_types():
    access_token = create_access_token(subject="42", role=UserRole.ADMIN)
    refresh_token = create_refresh_token(subject="42", role=UserRole.ADMIN)

    access_payload = decode_token(access_token, expected_type="access")
    refresh_payload = decode_token(refresh_token, expected_type="refresh")

    assert access_payload["sub"] == "42"
    assert access_payload["role"] == "admin"
    assert access_payload["typ"] == "access"
    assert refresh_payload["sub"] == "42"
    assert refresh_payload["typ"] == "refresh"


def test_refresh_decoder_rejects_access_token():
    access_token = create_access_token(subject="42", role=UserRole.ADMIN)

    try:
        decode_token(access_token, expected_type="refresh")
    except ValueError as exc:
        assert "Invalid token type" in str(exc)
    else:
        raise AssertionError("access token was accepted as refresh token")
```

- [ ] **Step 2: Run the security tests and verify RED**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_security.py -q
```

Expected: fail because `app.core.security` and `app.models.enums` do not exist.

- [ ] **Step 3: Add security dependencies**

Modify `backend/requirements.txt` by adding:

```text
email-validator>=2.2,<3
PyJWT>=2.10,<3
pwdlib[argon2]>=0.2,<1
```

Install after editing:

```bash
backend/.venv/bin/pip install -r backend/requirements.txt
```

- [ ] **Step 4: Add JWT settings**

Modify `backend/app/core/config.py`:

```python
class Settings(BaseSettings):
    app_environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://billing:billing@localhost:5432/billing"
    frontend_origin: str = "http://localhost:3000"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str = "local-development-secret-change-before-use"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    admin_bootstrap_token: str | None = None
```

- [ ] **Step 5: Create the role enum**

Create `backend/app/models/enums.py`:

```python
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    STAFF = "staff"
```

- [ ] **Step 6: Create security helpers**

Create `backend/app/core/security.py`:

```python
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.models.enums import UserRole


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def _create_token(subject: str, role: UserRole, token_type: str, expires_delta: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role.value,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, role: UserRole) -> str:
    settings = get_settings()
    return _create_token(
        subject=subject,
        role=role,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(subject: str, role: UserRole) -> str:
    settings = get_settings()
    return _create_token(
        subject=subject,
        role=role,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid token") from exc
    if payload.get("typ") != expected_type:
        raise ValueError("Invalid token type")
    return payload
```

- [ ] **Step 7: Run the security tests and verify GREEN**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_security.py -q
```

Expected: all tests in `test_security.py` pass.

---

### Task 2: SQLAlchemy Models and Alembic Migration

**Files:**

- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/mixins.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/company.py`
- Create: `backend/app/models/master_records.py`
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/20260825_0001_phase_1b_auth_master_records.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**

- Produces: `User`, `UserBranchAssignment`, `Company`, `Branch`, `Customer`, `Product`, `BankAccount`, `Transporter`, `TermsAndConditions`.
- Consumes: `Base` from `app.db.session` and `UserRole` from `app.models.enums`.

- [ ] **Step 1: Write the failing model tests**

Create `backend/tests/test_models.py`:

```python
from decimal import Decimal

from sqlalchemy import inspect

from app.models.company import Branch, Company
from app.models.enums import UserRole
from app.models.master_records import Customer, Product
from app.models.user import User, UserBranchAssignment


def test_user_branch_assignment_links_user_to_branch():
    assert User.__tablename__ == "users"
    assert UserBranchAssignment.__tablename__ == "user_branch_assignments"
    assert UserRole.ADMIN.value == "admin"
    assert "branch_id" in UserBranchAssignment.__table__.columns


def test_product_rates_use_decimal_numeric_columns():
    mapper = inspect(Product)
    column_names = {column.key for column in mapper.columns}

    assert {"base_rate", "gst_rate", "cess_rate"}.issubset(column_names)
    assert Product.__table__.c.base_rate.type.precision == 14
    assert Product.__table__.c.base_rate.type.scale == 4
    assert Product.__table__.c.gst_rate.type.precision == 5
    assert Product.__table__.c.gst_rate.type.scale == 2
    assert Product(base_rate=Decimal("10.2500"), gst_rate=Decimal("18.00"), cess_rate=Decimal("0.00")).base_rate == Decimal("10.2500")


def test_customer_has_separate_billing_and_shipping_address_columns():
    column_names = set(Customer.__table__.columns.keys())

    assert "billing_address_line1" in column_names
    assert "shipping_address_line1" in column_names
    assert "billing_state_code" in column_names
    assert "shipping_state_code" in column_names


def test_company_and_branch_gstin_context_is_explicit():
    assert Company.__tablename__ == "companies"
    assert Branch.__tablename__ == "branches"
    assert "gstin" in Branch.__table__.columns
    assert "company_id" in Branch.__table__.columns
```

- [ ] **Step 2: Run the model tests and verify RED**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_models.py -q
```

Expected: fail because the Phase 1B models do not exist.

- [ ] **Step 3: Create timestamp mixin**

Create `backend/app/models/mixins.py`:

```python
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
```

- [ ] **Step 4: Create user models**

Create `backend/app/models/user.py` with `User` and `UserBranchAssignment`. Use `SAEnum(UserRole, name="user_role", native_enum=False, validate_strings=True)` for `User.role`, unique email, `is_active=True`, and relationships to branch assignments.

- [ ] **Step 5: Create company and branch models**

Create `backend/app/models/company.py` with `Company` and `Branch`. Add uniqueness for branch GSTIN and branch relationship back to company.

- [ ] **Step 6: Create master-record models**

Create `backend/app/models/master_records.py`. Use `Numeric(14, 4)` for `Product.base_rate`, `Numeric(5, 2)` for `Product.gst_rate`, and `Numeric(5, 2)` for `Product.cess_rate`. Add `branch_id` foreign keys to every master model.

- [ ] **Step 7: Import models for metadata**

Create `backend/app/models/__init__.py`:

```python
from app.models.company import Branch, Company
from app.models.master_records import BankAccount, Customer, Product, TermsAndConditions, Transporter
from app.models.user import User, UserBranchAssignment

__all__ = [
    "BankAccount",
    "Branch",
    "Company",
    "Customer",
    "Product",
    "TermsAndConditions",
    "Transporter",
    "User",
    "UserBranchAssignment",
]
```

Modify `backend/alembic/env.py`:

```python
import app.models  # noqa: F401
```

Place the import after `from app.db.session import Base`.

- [ ] **Step 8: Create the Alembic migration**

Create `backend/alembic/versions/20260825_0001_phase_1b_auth_master_records.py` with `upgrade()` creating all Phase 1B tables and `downgrade()` dropping them in reverse dependency order. Use PostgreSQL-compatible `sa.Numeric(precision=14, scale=4)` and `sa.Numeric(precision=5, scale=2)` for product decimals.

- [ ] **Step 9: Run model tests and migration SQL**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_models.py -q
cd backend && ./.venv/bin/python -m alembic upgrade head --sql
```

Expected: model tests pass and Alembic renders SQL without errors.

---

### Task 3: Test Fixtures for Protected APIs

**Files:**

- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_fixtures.py`

**Interfaces:**

- Produces: pytest fixtures `db_session`, `client`, `company`, `branch`, `other_branch`, `admin_user`, `manager_user`, `staff_user`, `auth_headers(user)`.
- Consumes: `Base`, `get_db`, Phase 1B models, and security helpers.

- [ ] **Step 1: Write the failing fixture smoke tests**

Create `backend/tests/test_fixtures.py`:

```python
from app.models.enums import UserRole


def test_authenticated_fixture_headers_include_bearer_token(auth_headers, admin_user):
    headers = auth_headers(admin_user)

    assert headers["Authorization"].startswith("Bearer ")


def test_branch_fixtures_create_distinct_branches(branch, other_branch):
    assert branch.id != other_branch.id
    assert branch.gstin != other_branch.gstin


def test_user_fixtures_cover_all_roles(admin_user, manager_user, staff_user):
    assert admin_user.role == UserRole.ADMIN
    assert manager_user.role == UserRole.MANAGER
    assert staff_user.role == UserRole.STAFF
```

- [ ] **Step 2: Run fixture smoke tests and verify RED**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_fixtures.py -q
```

Expected: fail because `conftest.py` fixtures do not exist.

- [ ] **Step 3: Create isolated SQLAlchemy test fixtures**

Create `backend/tests/conftest.py` using `sqlite+pysqlite:///:memory:`, `StaticPool`, and `app.dependency_overrides[get_db]`. Import `app.models` before `Base.metadata.create_all(bind=engine)`.

- [ ] **Step 4: Add test data factories**

In `conftest.py`, create persisted companies, two branches, and three users. Assign the Manager and Staff users to `branch`; leave `other_branch` unassigned to them. Hash fixture passwords with `hash_password("password123")`.

- [ ] **Step 5: Add auth header helper**

In `conftest.py`, add:

```python
@pytest.fixture()
def auth_headers():
    def _headers(user):
        token = create_access_token(subject=str(user.id), role=user.role)
        return {"Authorization": f"Bearer {token}"}

    return _headers
```

- [ ] **Step 6: Run fixture smoke tests and verify GREEN**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_fixtures.py -q
```

Expected: all fixture smoke tests pass.

---

### Task 4: Authentication API

**Files:**

- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/schemas/user.py`
- Create: `backend/app/api/dependencies.py`
- Create: `backend/app/api/v1/auth.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**

- Produces: `get_current_user`, `get_current_active_user`, `require_roles`, `LoginRequest`, `TokenResponse`, `CurrentUserResponse`.
- Consumes: `User`, `UserBranchAssignment`, `hash_password`, `verify_password`, `create_access_token`, `create_refresh_token`, `decode_token`.

- [ ] **Step 1: Write failing auth route tests**

Create `backend/tests/test_auth.py`:

```python
def test_login_returns_access_refresh_and_user(client, staff_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": staff_user.email, "password": "password123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == staff_user.email
    assert body["user"]["role"] == "staff"
    assert body["user"]["branch_ids"]


def test_login_rejects_bad_password(client, staff_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": staff_user.email, "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_me_returns_current_user(client, auth_headers, manager_user):
    response = client.get("/api/v1/auth/me", headers=auth_headers(manager_user))

    assert response.status_code == 200
    assert response.json()["email"] == manager_user.email
    assert response.json()["role"] == "manager"


def test_refresh_returns_new_access_token(client, staff_user):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": staff_user.email, "password": "password123"},
    ).json()

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"


def test_refresh_rejects_access_token(client, staff_user):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": staff_user.email, "password": "password123"},
    ).json()

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": login["access_token"]})

    assert response.status_code == 401
```

- [ ] **Step 2: Run auth route tests and verify RED**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_auth.py -q
```

Expected: fail with `404 Not Found` for `/api/v1/auth/login`.

- [ ] **Step 3: Create auth and user schemas**

Create `backend/app/schemas/auth.py` and `backend/app/schemas/user.py`. Use `EmailStr` for emails. Return `branch_ids: list[int]` in user responses. Do not return password hashes.

- [ ] **Step 4: Create authentication dependencies**

Create `backend/app/api/dependencies.py`. Use `HTTPBearer(auto_error=False)`. `get_current_user` decodes access tokens, loads the active user from the database, and returns `401` on missing, invalid, expired, or inactive users.

- [ ] **Step 5: Create auth router**

Create `backend/app/api/v1/auth.py` with `POST /login`, `POST /refresh`, and `GET /me`. Login normalizes email with `strip().lower()` before lookup.

- [ ] **Step 6: Register auth router**

Modify `backend/app/api/v1/router.py`:

```python
from app.api.v1 import auth

router.include_router(auth.router, prefix="/auth", tags=["auth"])
```

- [ ] **Step 7: Run auth route tests and verify GREEN**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_auth.py -q
```

Expected: all auth route tests pass.

---

### Task 5: Guarded Admin Bootstrap and User Management API

**Files:**

- Modify: `.env.example`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/api/v1/auth.py`
- Create: `backend/app/api/v1/users.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_users.py`

**Interfaces:**

- Produces: `POST /api/v1/auth/bootstrap-admin`, `POST /api/v1/users`, `GET /api/v1/users`, `GET /api/v1/users/{user_id}`, `PATCH /api/v1/users/{user_id}`.
- Consumes: `require_roles(UserRole.ADMIN)`, `hash_password`, `User`, `UserBranchAssignment`, `Branch`.

- [ ] **Step 1: Write failing user API tests**

Create `backend/tests/test_users.py`:

```python
def test_admin_can_create_manager_with_branch_assignment(client, auth_headers, admin_user, branch):
    response = client.post(
        "/api/v1/users",
        headers=auth_headers(admin_user),
        json={
            "email": "manager.new@example.com",
            "full_name": "New Manager",
            "password": "StrongerPassword123",
            "role": "manager",
            "branch_ids": [branch.id],
            "is_active": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "manager.new@example.com"
    assert body["role"] == "manager"
    assert body["branch_ids"] == [branch.id]
    assert "hashed_password" not in body


def test_staff_cannot_create_users(client, auth_headers, staff_user, branch):
    response = client.post(
        "/api/v1/users",
        headers=auth_headers(staff_user),
        json={
            "email": "blocked@example.com",
            "full_name": "Blocked User",
            "password": "StrongerPassword123",
            "role": "staff",
            "branch_ids": [branch.id],
            "is_active": True,
        },
    )

    assert response.status_code == 403


def test_bootstrap_admin_requires_configured_token(client):
    response = client.post(
        "/api/v1/auth/bootstrap-admin",
        json={
            "email": "first.admin@example.com",
            "full_name": "First Admin",
            "password": "StrongerPassword123",
        },
    )

    assert response.status_code in {403, 409}
```

- [ ] **Step 2: Run user API tests and verify RED**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_users.py -q
```

Expected: fail with `404 Not Found` for `/api/v1/users`.

- [ ] **Step 3: Add bootstrap environment docs**

Modify `.env.example`:

```text
# Security
JWT_SECRET_KEY=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=14
ADMIN_BOOTSTRAP_TOKEN=replace-with-a-one-time-random-token
```

- [ ] **Step 4: Add guarded admin bootstrap**

In `backend/app/api/v1/auth.py`, add `POST /bootstrap-admin`. It must require `settings.admin_bootstrap_token`, require header `X-Setup-Token` to match it, create an Admin user only when the users table is empty, and return `409` once any user exists.

- [ ] **Step 5: Add user-management schemas**

In `backend/app/schemas/user.py`, add `UserCreate`, `UserUpdate`, and `UserRead`.

- [ ] **Step 6: Add user-management router**

Create `backend/app/api/v1/users.py`. Enforce Admin role on create, list, and patch. Allow `GET /users/{user_id}` for Admin or the same authenticated user.

- [ ] **Step 7: Register user router**

Modify `backend/app/api/v1/router.py`:

```python
from app.api.v1 import users

router.include_router(users.router, prefix="/users", tags=["users"])
```

- [ ] **Step 8: Run user API tests and verify GREEN**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_users.py -q
```

Expected: all user API tests pass.

---

### Task 6: Company and Branch APIs with Branch Scope

**Files:**

- Create: `backend/app/schemas/company.py`
- Create: `backend/app/schemas/branch.py`
- Modify: `backend/app/api/dependencies.py`
- Create: `backend/app/api/v1/companies.py`
- Create: `backend/app/api/v1/branches.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_permissions.py`

**Interfaces:**

- Produces: `assigned_branch_ids(user: User) -> set[int]`, `can_access_branch(user: User, branch_id: int) -> bool`, `ensure_branch_access(user: User, branch_id: int) -> None`, company routes, branch routes.
- Consumes: `UserRole`, `Company`, `Branch`, `UserBranchAssignment`.

- [ ] **Step 1: Write failing branch permission tests**

Create `backend/tests/test_permissions.py`:

```python
def test_admin_can_list_all_branches(client, auth_headers, admin_user, branch, other_branch):
    response = client.get("/api/v1/branches", headers=auth_headers(admin_user))

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert {branch.id, other_branch.id}.issubset(ids)


def test_manager_lists_only_assigned_branches(client, auth_headers, manager_user, branch, other_branch):
    response = client.get("/api/v1/branches", headers=auth_headers(manager_user))

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert branch.id in ids
    assert other_branch.id not in ids


def test_manager_cannot_read_unassigned_branch(client, auth_headers, manager_user, other_branch):
    response = client.get(f"/api/v1/branches/{other_branch.id}", headers=auth_headers(manager_user))

    assert response.status_code == 403


def test_staff_cannot_create_branch(client, auth_headers, staff_user, company):
    response = client.post(
        "/api/v1/branches",
        headers=auth_headers(staff_user),
        json={
            "company_id": company.id,
            "name": "Blocked Branch",
            "gstin": "29ABCDE1234F2Z7",
            "address_line1": "Blocked Street",
            "city": "Bengaluru",
            "state": "Karnataka",
            "state_code": "29",
            "postal_code": "560001",
            "is_active": True,
        },
    )

    assert response.status_code == 403
```

- [ ] **Step 2: Run branch permission tests and verify RED**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_permissions.py -q
```

Expected: fail with `404 Not Found` for `/api/v1/branches`.

- [ ] **Step 3: Add shared branch-scope helpers**

Modify `backend/app/api/dependencies.py` to add:

```python
def assigned_branch_ids(user: User) -> set[int]:
    return {assignment.branch_id for assignment in user.branch_assignments}


def can_access_branch(user: User, branch_id: int) -> bool:
    return user.role == UserRole.ADMIN or branch_id in assigned_branch_ids(user)


def ensure_branch_access(user: User, branch_id: int) -> None:
    if not can_access_branch(user, branch_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Branch access denied")
```

- [ ] **Step 4: Create company and branch schemas**

Create `backend/app/schemas/company.py` and `backend/app/schemas/branch.py`. Enforce GSTIN length 15 on branch payloads.

- [ ] **Step 5: Create company and branch routers**

Create `backend/app/api/v1/companies.py` and `backend/app/api/v1/branches.py`. Admin can create and patch. Authenticated non-admin users can list and read only companies/branches reachable through assigned branches.

- [ ] **Step 6: Register company and branch routers**

Modify `backend/app/api/v1/router.py`:

```python
from app.api.v1 import branches, companies

router.include_router(companies.router, prefix="/companies", tags=["companies"])
router.include_router(branches.router, prefix="/branches", tags=["branches"])
```

- [ ] **Step 7: Run branch permission tests and verify GREEN**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_permissions.py -q
```

Expected: all permission tests pass.

---

### Task 7: Customer and Product Master APIs

**Files:**

- Create: `backend/app/schemas/common.py`
- Create: `backend/app/schemas/master_records.py`
- Create: `backend/app/api/v1/customers.py`
- Create: `backend/app/api/v1/products.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_master_records.py`

**Interfaces:**

- Produces: customer create/list/read/patch routes and product create/list/read/patch routes.
- Consumes: `ensure_branch_access`, `Customer`, `Product`, `AddressSchema`, and decimal validators.

- [ ] **Step 1: Write failing customer and product tests**

Create `backend/tests/test_master_records.py`:

```python
from decimal import Decimal


def test_staff_can_create_customer_for_assigned_branch(client, auth_headers, staff_user, branch):
    response = client.post(
        "/api/v1/customers",
        headers=auth_headers(staff_user),
        json={
            "branch_id": branch.id,
            "name": "Apex Laboratories",
            "gstin": "29ABCDE1234F1Z5",
            "pan": "ABCDE1234F",
            "email": "billing@apex.example",
            "phone": "9876543210",
            "billing_address": {
                "name": "Apex Billing",
                "address_line1": "Billing Street 1",
                "address_line2": "Industrial Area",
                "city": "Bengaluru",
                "state": "Karnataka",
                "state_code": "29",
                "postal_code": "560001",
            },
            "shipping_address": {
                "name": "Apex Consignee",
                "address_line1": "Shipping Street 2",
                "address_line2": "Warehouse Block",
                "city": "Mysuru",
                "state": "Karnataka",
                "state_code": "29",
                "postal_code": "570001",
            },
            "is_active": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["billing_address"]["address_line1"] == "Billing Street 1"
    assert body["shipping_address"]["address_line1"] == "Shipping Street 2"


def test_staff_cannot_create_customer_for_unassigned_branch(client, auth_headers, staff_user, other_branch):
    response = client.post(
        "/api/v1/customers",
        headers=auth_headers(staff_user),
        json={
            "branch_id": other_branch.id,
            "name": "Blocked Customer",
            "billing_address": {
                "name": "Blocked Billing",
                "address_line1": "Blocked",
                "city": "Mumbai",
                "state": "Maharashtra",
                "state_code": "27",
                "postal_code": "400001",
            },
            "shipping_address": {
                "name": "Blocked Shipping",
                "address_line1": "Blocked",
                "city": "Mumbai",
                "state": "Maharashtra",
                "state_code": "27",
                "postal_code": "400001",
            },
            "is_active": True,
        },
    )

    assert response.status_code == 403


def test_manager_can_create_product_with_decimal_rates(client, auth_headers, manager_user, branch):
    response = client.post(
        "/api/v1/products",
        headers=auth_headers(manager_user),
        json={
            "branch_id": branch.id,
            "name": "Sodium Citrate",
            "description": "Tri-sodium citrate dihydrate",
            "hsn_sac": "29181590",
            "unit": "KG",
            "base_rate": "128.7500",
            "gst_rate": "18.00",
            "cess_rate": "0.00",
            "is_active": True,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["base_rate"] == "128.7500"
    assert body["gst_rate"] == "18.00"
    assert body["cess_rate"] == "0.00"


def test_product_rejects_negative_rates(client, auth_headers, manager_user, branch):
    response = client.post(
        "/api/v1/products",
        headers=auth_headers(manager_user),
        json={
            "branch_id": branch.id,
            "name": "Invalid Product",
            "description": "Invalid rate",
            "hsn_sac": "29181590",
            "unit": "KG",
            "base_rate": "-1.0000",
            "gst_rate": "18.00",
            "cess_rate": "0.00",
            "is_active": True,
        },
    )

    assert response.status_code == 422
```

- [ ] **Step 2: Run master-record tests and verify RED**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_master_records.py -q
```

Expected: fail with `404 Not Found` for `/api/v1/customers` and `/api/v1/products`.

- [ ] **Step 3: Create shared schemas**

Create `backend/app/schemas/common.py` with `AddressPayload`, `AddressRead`, and a shared decimal serializer:

```python
from decimal import Decimal


def serialize_decimal(value: Decimal) -> str:
    return str(value)
```

- [ ] **Step 4: Create customer and product schemas**

In `backend/app/schemas/master_records.py`, define `CustomerCreate`, `CustomerUpdate`, `CustomerRead`, `ProductCreate`, `ProductUpdate`, and `ProductRead`. Use nested `billing_address` and `shipping_address` payloads for customers. Use Pydantic decimal fields for product rates with `ge=Decimal("0")`.

- [ ] **Step 5: Create customer router**

Create `backend/app/api/v1/customers.py`. On create and patch, call `ensure_branch_access` before writing. On list, filter by requested `branch_id` when supplied and by assigned branches for non-admin users.

- [ ] **Step 6: Create product router**

Create `backend/app/api/v1/products.py`. Preserve Decimal values through SQLAlchemy and response serialization. Do not convert product rates to floats.

- [ ] **Step 7: Register customer and product routers**

Modify `backend/app/api/v1/router.py`:

```python
from app.api.v1 import customers, products

router.include_router(customers.router, prefix="/customers", tags=["customers"])
router.include_router(products.router, prefix="/products", tags=["products"])
```

- [ ] **Step 8: Run customer and product tests and verify GREEN**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_master_records.py -q
```

Expected: all tests in `test_master_records.py` pass.

---

### Task 8: Remaining Master APIs

**Files:**

- Modify: `backend/app/schemas/master_records.py`
- Create: `backend/app/api/v1/bank_accounts.py`
- Create: `backend/app/api/v1/transporters.py`
- Create: `backend/app/api/v1/terms.py`
- Modify: `backend/app/api/v1/router.py`
- Test: `backend/tests/test_remaining_masters.py`

**Interfaces:**

- Produces: bank-account, transporter, and terms-and-conditions create/list/read/patch routes.
- Consumes: `ensure_branch_access`, `BankAccount`, `Transporter`, `TermsAndConditions`.

- [ ] **Step 1: Write failing remaining-master tests**

Create `backend/tests/test_remaining_masters.py`:

```python
def test_admin_can_create_bank_account(client, auth_headers, admin_user, branch):
    response = client.post(
        "/api/v1/bank-accounts",
        headers=auth_headers(admin_user),
        json={
            "branch_id": branch.id,
            "bank_name": "State Bank of India",
            "account_name": "Pristine Bio",
            "account_number": "12345678901",
            "ifsc_code": "SBIN0001234",
            "branch_name": "Bengaluru Main",
            "is_default": True,
            "is_active": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["ifsc_code"] == "SBIN0001234"


def test_manager_can_create_transporter_for_assigned_branch(client, auth_headers, manager_user, branch):
    response = client.post(
        "/api/v1/transporters",
        headers=auth_headers(manager_user),
        json={
            "branch_id": branch.id,
            "name": "Rapid Logistics",
            "gstin": "29ABCDE1234F1Z5",
            "phone": "9876543210",
            "vehicle_number": "KA01AB1234",
            "is_active": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Rapid Logistics"


def test_staff_cannot_create_terms_for_unassigned_branch(client, auth_headers, staff_user, other_branch):
    response = client.post(
        "/api/v1/terms-and-conditions",
        headers=auth_headers(staff_user),
        json={
            "branch_id": other_branch.id,
            "title": "Blocked Terms",
            "body": "Payment due within 30 days.",
            "is_default": False,
            "is_active": True,
        },
    )

    assert response.status_code == 403


def test_staff_can_list_terms_for_assigned_branch(client, auth_headers, staff_user, branch):
    create_response = client.post(
        "/api/v1/terms-and-conditions",
        headers=auth_headers(staff_user),
        json={
            "branch_id": branch.id,
            "title": "Standard Terms",
            "body": "Payment due within 30 days.",
            "is_default": True,
            "is_active": True,
        },
    )

    assert create_response.status_code == 201
    response = client.get(f"/api/v1/terms-and-conditions?branch_id={branch.id}", headers=auth_headers(staff_user))
    assert response.status_code == 200
    assert response.json()[0]["title"] == "Standard Terms"
```

- [ ] **Step 2: Run remaining-master tests and verify RED**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_remaining_masters.py -q
```

Expected: fail with `404 Not Found` for the remaining master endpoints.

- [ ] **Step 3: Extend master schemas**

Add `BankAccountCreate`, `BankAccountUpdate`, `BankAccountRead`, `TransporterCreate`, `TransporterUpdate`, `TransporterRead`, `TermsCreate`, `TermsUpdate`, and `TermsRead` to `backend/app/schemas/master_records.py`.

- [ ] **Step 4: Create remaining master routers**

Create `backend/app/api/v1/bank_accounts.py`, `backend/app/api/v1/transporters.py`, and `backend/app/api/v1/terms.py`. Each router must enforce branch access on create/read/patch and list assigned branches only for non-admin users.

- [ ] **Step 5: Register remaining master routers**

Modify `backend/app/api/v1/router.py`:

```python
from app.api.v1 import bank_accounts, terms, transporters

router.include_router(bank_accounts.router, prefix="/bank-accounts", tags=["bank-accounts"])
router.include_router(transporters.router, prefix="/transporters", tags=["transporters"])
router.include_router(terms.router, prefix="/terms-and-conditions", tags=["terms-and-conditions"])
```

- [ ] **Step 6: Run remaining-master tests and verify GREEN**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_remaining_masters.py -q
```

Expected: all tests in `test_remaining_masters.py` pass.

---

### Task 9: Frontend API Client and Shared Shell

**Files:**

- Create: `frontend/app/lib/types.ts`
- Create: `frontend/app/lib/api.ts`
- Create: `frontend/app/components/AppShell.tsx`
- Create: `frontend/app/components/AuthGate.tsx`
- Modify: `frontend/app/page.tsx`

**Interfaces:**

- Produces: `apiRequest<T>()`, `getStoredSession()`, `storeSession()`, `clearSession()`, `AppShell`, `AuthGate`.
- Consumes: `NEXT_PUBLIC_API_BASE_URL`.

- [ ] **Step 1: Move shell into reusable component**

Create `frontend/app/components/AppShell.tsx` using the existing dashboard sidebar/header visual language. Navigation items must link to `/`, `/customers`, `/products`, `/branches`, `/bank-accounts`, `/transporters`, `/terms`, and `/settings`.

- [ ] **Step 2: Create API types**

Create `frontend/app/lib/types.ts` with `User`, `TokenResponse`, `Branch`, `Customer`, `Product`, `BankAccount`, `Transporter`, and `TermsAndConditions` types. Decimal API fields must be typed as `string`.

- [ ] **Step 3: Create API helper**

Create `frontend/app/lib/api.ts` as a client-only module. It must read/write tokens from `localStorage`, attach `Authorization: Bearer <access_token>`, use `process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"`, and throw an `ApiError` containing status and message.

- [ ] **Step 4: Create auth gate**

Create `frontend/app/components/AuthGate.tsx`. It must render children when a stored session exists and render a compact login link state when there is no stored session.

- [ ] **Step 5: Update dashboard page**

Modify `frontend/app/page.tsx` to wrap the existing dashboard content in `AppShell` and keep the existing demonstration summary cards. Update the phase label from Phase 1A to Phase 1B.

- [ ] **Step 6: Run frontend type-check**

Run:

```bash
cd frontend && npm run type-check
```

Expected: type-check passes.

---

### Task 10: Frontend Login and Management Screens

**Files:**

- Create: `frontend/app/components/MasterDataPage.tsx`
- Create: `frontend/app/login/page.tsx`
- Create: `frontend/app/branches/page.tsx`
- Create: `frontend/app/customers/page.tsx`
- Create: `frontend/app/products/page.tsx`
- Create: `frontend/app/bank-accounts/page.tsx`
- Create: `frontend/app/transporters/page.tsx`
- Create: `frontend/app/terms/page.tsx`
- Create: `frontend/app/settings/page.tsx`

**Interfaces:**

- Produces: basic forms and tables for each Phase 1B master route.
- Consumes: `AppShell`, `AuthGate`, `apiRequest`, and types from `frontend/app/lib/types.ts`.

- [ ] **Step 1: Create reusable master page component**

Create `frontend/app/components/MasterDataPage.tsx` with a client component that accepts:

```typescript
type FieldConfig = {
  name: string;
  label: string;
  type?: "text" | "email" | "number" | "textarea" | "checkbox";
  required?: boolean;
};

type MasterDataPageProps = {
  title: string;
  description: string;
  endpoint: string;
  fields: FieldConfig[];
  columns: { key: string; label: string }[];
  initialForm: Record<string, string | boolean>;
};
```

It must list records, submit create requests, show server errors, and refresh the list after create.

- [ ] **Step 2: Create login page**

Create `frontend/app/login/page.tsx` with email/password inputs, submit to `/auth/login`, store the returned session, and navigate to `/`.

- [ ] **Step 3: Create branch management page**

Create `frontend/app/branches/page.tsx` with fields `company_id`, `name`, `gstin`, `address_line1`, `address_line2`, `city`, `state`, `state_code`, `postal_code`, `phone`, `email`, and `is_active`.

- [ ] **Step 4: Create customer management page**

Create `frontend/app/customers/page.tsx` with fields for `branch_id`, identity/contact fields, and flattened billing/shipping address form names. Transform the form into nested `billing_address` and `shipping_address` objects before submitting.

- [ ] **Step 5: Create product management page**

Create `frontend/app/products/page.tsx` with fields `branch_id`, `name`, `description`, `hsn_sac`, `unit`, `base_rate`, `gst_rate`, `cess_rate`, and `is_active`.

- [ ] **Step 6: Create remaining master pages**

Create `frontend/app/bank-accounts/page.tsx`, `frontend/app/transporters/page.tsx`, and `frontend/app/terms/page.tsx` with endpoint-specific fields matching the backend schemas.

- [ ] **Step 7: Create settings page**

Create `frontend/app/settings/page.tsx` to call `/auth/me` and display email, full name, role, and branch ids.

- [ ] **Step 8: Run frontend checks**

Run:

```bash
cd frontend && npm run type-check
cd frontend && npm run build
```

Expected: type-check and production build pass.

---

### Task 11: Final Verification and Project Status

**Files:**

- Modify: `docs/PROJECT_STATUS.md`

**Interfaces:**

- Consumes: all Phase 1B implementation files.
- Produces: final status record with completed work, verification commands, results, exact next phase, and blockers.

- [ ] **Step 1: Run backend targeted suites**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest tests/test_security.py tests/test_auth.py tests/test_users.py tests/test_permissions.py tests/test_master_records.py tests/test_remaining_masters.py -q
```

Expected: targeted Phase 1B tests pass.

- [ ] **Step 2: Run backend full suite**

Run:

```bash
cd backend && ./.venv/bin/python -m pytest -q
```

Expected: full backend suite passes.

- [ ] **Step 3: Run Alembic offline verification**

Run:

```bash
cd backend && ./.venv/bin/python -m alembic upgrade head --sql
```

Expected: migration SQL renders without errors.

- [ ] **Step 4: Run frontend production checks**

Run:

```bash
cd frontend && npm run type-check
cd frontend && npm run build
```

Expected: frontend type-check and production build pass.

- [ ] **Step 5: Run Docker Compose validation**

Run:

```bash
docker compose config
```

Expected when Docker is installed: Compose config renders successfully.

If Docker is unavailable, record the exact `docker: command not found` blocker and run:

```bash
backend/.venv/bin/python -c 'from pathlib import Path; import yaml; data = yaml.safe_load(Path("docker-compose.yml").read_text()); assert set(data["services"]) == {"frontend", "backend", "postgres", "redis"}; print("compose YAML parsed; services:", ", ".join(sorted(data["services"])))'
```

Expected fallback: Compose YAML parses and reports `backend`, `frontend`, `postgres`, and `redis`.

- [ ] **Step 6: Update project status**

Modify `docs/PROJECT_STATUS.md` to set the current phase to Phase 1B, record completed work, record every command run and result, record real blockers, and set the exact next phase as Phase 1C invoice draft and approval lifecycle foundation. State that Phase 1C has not started.

- [ ] **Step 7: Final scope check**

Run a focused search:

```bash
rg -n "invoice calculation|pdf|IRN|e-way|inventory|batch|lot|celery" backend frontend docs/PROJECT_STATUS.md
```

Expected: matches only in explicit out-of-scope documentation or existing navigation copy; no Phase 1C or future-phase implementation exists.

## Plan Self-Review

- Spec coverage: authentication, roles, branch-scoped authorization, company/branch models, all requested master records, Alembic migration, APIs, screens, tests, and status update are covered by tasks.
- Placeholder scan: this plan has concrete file paths, commands, route names, fields, and test examples.
- Type consistency: backend route and model names match the approved spec; frontend Decimal-bearing fields are typed as strings to preserve values received from the API.
- Scope check: invoice calculations, PDF generation, GST APIs, inventory movement, batch/lot behavior, Celery, and Android behavior are explicitly excluded.
