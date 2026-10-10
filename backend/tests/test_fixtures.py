from app.models.enums import UserRole


def test_authenticated_fixture_headers_include_cookie_and_csrf(auth_headers, admin_user):
    headers = auth_headers(admin_user)

    assert "billing_access=" in headers["Cookie"]
    assert headers["X-CSRF-Token"] and headers["Origin"]
    assert "Authorization" not in headers


def test_branch_fixtures_create_distinct_branches(branch, other_branch):
    assert branch.id != other_branch.id
    assert branch.gstin != other_branch.gstin


def test_user_fixtures_cover_all_roles(admin_user, manager_user, staff_user):
    assert admin_user.role == UserRole.ADMIN
    assert manager_user.role == UserRole.MANAGER
    assert staff_user.role == UserRole.STAFF
