from app.core.config import get_settings
from app.core.security import verify_password
from app.models.enums import UserRole
from app.models.user import User, UserBranchAssignment


def test_register_creates_active_admin_with_master_password(
    client, db_session, monkeypatch
):
    monkeypatch.setenv("ADMIN_REGISTRATION_MASTER_PASSWORD", "MasterKey123")
    get_settings.cache_clear()

    try:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": " NEW.ADMIN@EXAMPLE.COM ",
                "full_name": "New Admin",
                "password": "Abc123",
                "master_password": "MasterKey123",
            },
        )
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "new.admin@example.com", "password": "Abc123"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "new.admin@example.com"
        assert body["full_name"] == "New Admin"
        assert body["role"] == "admin"
        assert body["branch_ids"] == []
        assert body["is_active"] is True
        assert "hashed_password" not in body
        assert login_response.status_code == 200
        assert login_response.json()["access_token"]
        assert login_response.json()["refresh_token"]

        user = db_session.query(User).filter_by(email="new.admin@example.com").one()
        assert user.role == UserRole.ADMIN
        assert user.is_active is True
        assert verify_password("Abc123", user.hashed_password)
        assert db_session.query(UserBranchAssignment).filter_by(user_id=user.id).count() == 0
    finally:
        get_settings.cache_clear()


def test_register_fails_closed_when_master_password_is_not_configured(
    client, db_session, monkeypatch
):
    monkeypatch.delenv("ADMIN_REGISTRATION_MASTER_PASSWORD", raising=False)
    get_settings.cache_clear()

    try:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "missing.master@example.com",
                "full_name": "Missing Master",
                "password": "Abc123",
                "master_password": "MasterKey123",
            },
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Invalid master password"
        assert db_session.query(User).filter_by(email="missing.master@example.com").count() == 0
    finally:
        get_settings.cache_clear()


def test_register_rejects_wrong_master_password(client, db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_REGISTRATION_MASTER_PASSWORD", "MasterKey123")
    get_settings.cache_clear()

    try:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "wrong.master@example.com",
                "full_name": "Wrong Master",
                "password": "Abc123",
                "master_password": "WrongKey123",
            },
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Invalid master password"
        assert db_session.query(User).filter_by(email="wrong.master@example.com").count() == 0
    finally:
        get_settings.cache_clear()


def test_register_rejects_duplicate_email_case_insensitively(
    client, staff_user, monkeypatch
):
    monkeypatch.setenv("ADMIN_REGISTRATION_MASTER_PASSWORD", "MasterKey123")
    get_settings.cache_clear()

    try:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": f" {staff_user.email.upper()} ",
                "full_name": "Duplicate User",
                "password": "Abc123",
                "master_password": "MasterKey123",
            },
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "Email already exists"
    finally:
        get_settings.cache_clear()


def test_register_forbids_public_role_branch_and_active_fields(
    client, branch, monkeypatch
):
    monkeypatch.setenv("ADMIN_REGISTRATION_MASTER_PASSWORD", "MasterKey123")
    get_settings.cache_clear()

    try:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "escalation@example.com",
                "full_name": "Privilege Escalation",
                "password": "Abc123",
                "master_password": "MasterKey123",
                "role": "staff",
                "branch_ids": [branch.id],
                "is_active": False,
            },
        )

        assert response.status_code == 422
    finally:
        get_settings.cache_clear()


def test_register_rejects_weak_password(client, monkeypatch):
    monkeypatch.setenv("ADMIN_REGISTRATION_MASTER_PASSWORD", "MasterKey123")
    get_settings.cache_clear()

    try:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "weak.password@example.com",
                "full_name": "Weak Password",
                "password": "Abc1234",
                "master_password": "MasterKey123",
            },
        )

        assert response.status_code == 422
    finally:
        get_settings.cache_clear()


def test_register_rejects_password_longer_than_six_characters(client, monkeypatch):
    monkeypatch.setenv("ADMIN_REGISTRATION_MASTER_PASSWORD", "MasterKey123")
    get_settings.cache_clear()

    try:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "long.password@example.com",
                "full_name": "Long Password",
                "password": "SecurePass123",
                "master_password": "MasterKey123",
            },
        )

        assert response.status_code == 422
    finally:
        get_settings.cache_clear()


def test_admin_can_create_staff_after_login(client, auth_headers, admin_user, branch):
    response = client.post(
        "/api/v1/users",
        headers=auth_headers(admin_user),
        json={
            "email": "staff.by.admin@example.com",
            "full_name": "Staff By Admin",
            "password": "Abc123",
            "role": "staff",
            "branch_ids": [branch.id],
            "is_active": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "staff"
    assert response.json()["branch_ids"] == [branch.id]


def test_login_returns_access_refresh_and_user(client, staff_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": staff_user.email, "password": "Abc123"},
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
        json={"email": staff_user.email, "password": "Abc124"},
    )

    assert response.status_code == 401


def test_login_rejects_password_longer_than_six_characters(client, staff_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": staff_user.email, "password": "Abc1234"},
    )

    assert response.status_code == 422


def test_login_normalizes_whitespace_and_uppercase_email(client, staff_user):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": " STAFF@EXAMPLE.COM ", "password": "Abc123"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == staff_user.email


def test_login_rejects_inactive_user(client, db_session, staff_user):
    staff_user.is_active = False
    db_session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": staff_user.email, "password": "Abc123"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Account pending admin approval"


def test_me_returns_current_user(client, auth_headers, manager_user):
    response = client.get("/api/v1/auth/me", headers=auth_headers(manager_user))

    assert response.status_code == 200
    assert response.json()["email"] == manager_user.email
    assert response.json()["role"] == "manager"


def test_me_returns_authenticated_user_branch_ids(
    client, auth_headers, branch, manager_user
):
    response = client.get("/api/v1/auth/me", headers=auth_headers(manager_user))

    assert response.status_code == 200
    assert response.json()["branch_ids"] == [branch.id]


def test_refresh_returns_new_access_token(client, staff_user):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": staff_user.email, "password": "Abc123"},
    ).json()

    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"


def test_refresh_rejects_inactive_user(client, db_session, staff_user):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": staff_user.email, "password": "Abc123"},
    ).json()
    staff_user.is_active = False
    db_session.commit()

    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )

    assert response.status_code == 401


def test_refresh_rejects_access_token(client, staff_user):
    login = client.post(
        "/api/v1/auth/login",
        json={"email": staff_user.email, "password": "Abc123"},
    ).json()

    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": login["access_token"]})

    assert response.status_code == 401


def test_me_rejects_inactive_user(client, auth_headers, db_session, staff_user):
    staff_user.is_active = False
    db_session.commit()

    response = client.get("/api/v1/auth/me", headers=auth_headers(staff_user))

    assert response.status_code == 401
