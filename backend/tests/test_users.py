from types import SimpleNamespace
from unittest.mock import Mock

from app.api.v1 import auth
from app.core.config import get_settings
from app.models.enums import UserRole
from app.models.user import User
from sqlalchemy import func, select


def test_admin_can_create_manager_with_branch_assignment(
    client, auth_headers, admin_user, branch
):
    response = client.post(
        "/api/v1/users",
        headers=auth_headers(admin_user),
        json={
            "email": "manager.new@example.com",
            "full_name": "New Manager",
            "password": "Abc123",
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
            "password": "Abc123",
            "role": "staff",
            "branch_ids": [branch.id],
            "is_active": True,
        },
    )

    assert response.status_code == 403


def test_staff_cannot_list_users(client, auth_headers, staff_user):
    response = client.get("/api/v1/users", headers=auth_headers(staff_user))

    assert response.status_code == 403


def test_staff_cannot_patch_users(client, auth_headers, staff_user):
    response = client.patch(
        f"/api/v1/users/{staff_user.id}",
        headers=auth_headers(staff_user),
        json={"full_name": "Changed by Staff"},
    )

    assert response.status_code == 403


def test_admin_user_creation_rejects_password_longer_than_six(
    client, auth_headers, admin_user, branch
):
    response = client.post(
        "/api/v1/users",
        headers=auth_headers(admin_user),
        json={
            "email": "long.password.user@example.com",
            "full_name": "Long Password User",
            "password": "StrongerPassword123",
            "role": "staff",
            "branch_ids": [branch.id],
            "is_active": True,
        },
    )

    assert response.status_code == 422


def test_bootstrap_admin_requires_configured_token(client):
    response = client.post(
        "/api/v1/auth/bootstrap-admin",
        json={
            "email": "first.admin@example.com",
            "full_name": "First Admin",
            "password": "Abc123",
        },
    )

    assert response.status_code in {403, 409}


def test_bootstrap_admin_rejects_unset_token_when_no_users_exist(client, monkeypatch):
    monkeypatch.delenv("ADMIN_BOOTSTRAP_TOKEN", raising=False)
    get_settings.cache_clear()

    try:
        response = client.post(
            "/api/v1/auth/bootstrap-admin",
            json={
                "email": "first.admin@example.com",
                "full_name": "First Admin",
                "password": "Abc123",
            },
        )

        assert response.status_code == 403
    finally:
        get_settings.cache_clear()


def test_bootstrap_admin_rejects_mismatching_configured_token(client, monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", "correct-token")
    get_settings.cache_clear()

    try:
        response = client.post(
            "/api/v1/auth/bootstrap-admin",
            headers={"X-Setup-Token": "wrong-token"},
            json={
                "email": "first.admin@example.com",
                "full_name": "First Admin",
                "password": "Abc123",
            },
        )

        assert response.status_code == 403
    finally:
        get_settings.cache_clear()


def test_bootstrap_admin_returns_conflict_after_any_user_exists_without_token(
    client, admin_user
):
    response = client.post(
        "/api/v1/auth/bootstrap-admin",
        json={
            "email": "first.admin@example.com",
            "full_name": "First Admin",
            "password": "Abc123",
        },
    )

    assert response.status_code == 409


def test_bootstrap_lock_uses_postgresql_advisory_transaction_lock():
    db = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        execute=Mock(),
    )

    auth._lock_bootstrap_transaction(db)

    statement = db.execute.call_args.args[0]
    assert "pg_advisory_xact_lock" in str(statement)
    assert db.execute.call_args.args[1] == {"key": auth._BOOTSTRAP_LOCK_KEY}


def test_bootstrap_admin_creates_only_first_user(client, db_session, monkeypatch):
    monkeypatch.setenv("ADMIN_BOOTSTRAP_TOKEN", "setup-token")
    get_settings.cache_clear()

    try:
        first_response = client.post(
            "/api/v1/auth/bootstrap-admin",
            headers={"X-Setup-Token": "setup-token"},
            json={
                "email": "first.admin@example.com",
                "full_name": "First Admin",
                "password": "Abc123",
            },
        )
        second_response = client.post(
            "/api/v1/auth/bootstrap-admin",
            headers={"X-Setup-Token": "setup-token"},
            json={
                "email": "second.admin@example.com",
                "full_name": "Second Admin",
                "password": "Abc123",
            },
        )

        assert first_response.status_code == 201
        assert first_response.json()["role"] == "admin"
        assert "hashed_password" not in first_response.json()
        assert second_response.status_code == 409
        assert db_session.scalar(select(func.count()).select_from(User)) == 1
    finally:
        get_settings.cache_clear()


def test_user_creation_rejects_unknown_branch_id(client, auth_headers, admin_user):
    response = client.post(
        "/api/v1/users",
        headers=auth_headers(admin_user),
        json={
            "email": "unknown.branch@example.com",
            "full_name": "Unknown Branch",
            "password": "Abc123",
            "role": "staff",
            "branch_ids": [9999],
            "is_active": True,
        },
    )

    assert response.status_code == 422


def test_user_creation_rejects_duplicate_branch_ids(
    client, auth_headers, admin_user, branch
):
    response = client.post(
        "/api/v1/users",
        headers=auth_headers(admin_user),
        json={
            "email": "duplicate.branch@example.com",
            "full_name": "Duplicate Branch",
            "password": "Abc123",
            "role": "staff",
            "branch_ids": [branch.id, branch.id],
            "is_active": True,
        },
    )

    assert response.status_code == 422


def test_user_can_read_own_profile_but_not_another_user(
    client, auth_headers, manager_user, staff_user
):
    own_response = client.get(
        f"/api/v1/users/{manager_user.id}", headers=auth_headers(manager_user)
    )
    other_response = client.get(
        f"/api/v1/users/{staff_user.id}", headers=auth_headers(manager_user)
    )

    assert own_response.status_code == 200
    assert own_response.json()["id"] == manager_user.id
    assert "hashed_password" not in own_response.json()
    assert other_response.status_code == 403


def test_admin_can_list_and_patch_user_branch_assignments(
    client, auth_headers, admin_user, staff_user, other_branch
):
    list_response = client.get("/api/v1/users", headers=auth_headers(admin_user))
    patch_response = client.patch(
        f"/api/v1/users/{staff_user.id}",
        headers=auth_headers(admin_user),
        json={"role": UserRole.MANAGER.value, "branch_ids": [other_branch.id]},
    )

    assert list_response.status_code == 200
    assert {user["id"] for user in list_response.json()} >= {
        admin_user.id,
        staff_user.id,
    }
    assert all("hashed_password" not in user for user in list_response.json())
    assert patch_response.status_code == 200
    assert patch_response.json()["role"] == "manager"
    assert patch_response.json()["branch_ids"] == [other_branch.id]
