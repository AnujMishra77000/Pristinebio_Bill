import pytest
from app.models.enums import UserRole


def test_admin_must_use_invitations_not_direct_password_creation(client,admin_user,auth_headers):
    assert client.post("/api/v1/users",headers=auth_headers(admin_user),json={}).status_code==410


def test_staff_cannot_manage_accounts(client,staff_user,admin_user,auth_headers):
    headers=auth_headers(staff_user)
    assert client.post("/api/v1/users",headers=headers,json={}).status_code==403
    assert client.get("/api/v1/users",headers=headers).status_code==403
    assert client.patch(f"/api/v1/users/{admin_user.id}",headers=headers,json={"is_active":False}).status_code==403


@pytest.mark.parametrize("ids",[[999999],[1,1],[]])
def test_invitation_validates_staff_assignments(client,admin_user,branch,auth_headers,ids):
    response=client.post("/api/v1/auth/invitations",headers=auth_headers(admin_user),json={"email":"new@example.com","role":"staff","branch_ids":ids})
    assert response.status_code==422


def test_user_can_read_own_but_not_other_profile(client,manager_user,staff_user,auth_headers):
    headers=auth_headers(manager_user)
    own=client.get(f"/api/v1/users/{manager_user.id}",headers=headers)
    assert own.status_code==200 and "hashed_password" not in own.json()
    assert client.get(f"/api/v1/users/{staff_user.id}",headers=headers).status_code==403


def test_admin_can_list_and_patch_assignments(client,admin_user,staff_user,other_branch,auth_headers):
    headers=auth_headers(admin_user)
    response=client.get("/api/v1/users",headers=headers)
    assert response.status_code==200 and all("hashed_password" not in u for u in response.json())
    updated=client.patch(f"/api/v1/users/{staff_user.id}",headers=headers,json={"role":UserRole.MANAGER.value,"branch_ids":[other_branch.id]})
    assert updated.status_code==200,updated.text
    assert updated.json()["branch_ids"]==[other_branch.id] and updated.json()["role"]=="manager"


def test_disabled_or_unknown_assignments_are_rejected(client,admin_user,staff_user,branch,db_session,auth_headers):
    branch.is_active=False
    db_session.commit()
    assert client.patch(f"/api/v1/users/{staff_user.id}",headers=auth_headers(admin_user),json={"branch_ids":[branch.id]}).status_code==422
