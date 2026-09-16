from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models.company import Branch
from app.models.enums import UserRole
from app.models.user import User


security_scheme = HTTPBearer(auto_error=False)


def _authentication_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security_scheme)
    ],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None:
        raise _authentication_exception()

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise _authentication_exception() from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _authentication_exception()
    return user


def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user


def require_roles(*roles: UserRole):
    def role_dependency(
        current_user: Annotated[User, Depends(get_current_active_user)],
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return role_dependency


def assigned_branch_ids(user: User) -> set[int]:
    return {assignment.branch_id for assignment in user.branch_assignments}


def can_access_branch(user: User, branch_id: int) -> bool:
    return user.role == UserRole.ADMIN or branch_id in assigned_branch_ids(user)


def ensure_branch_access(user: User, branch_id: int) -> None:
    if not can_access_branch(user, branch_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seller/GST profile access denied",
        )


def default_branch_for_user(db: Session, user: User) -> Branch:
    statement = select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.id)
    if user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(user)
        statement = statement.where(Branch.id.in_(assigned) if assigned else false())
    branch = db.scalar(statement)
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Seller/GST profile is not configured for this user",
        )
    return branch


def resolve_branch_for_user(db: Session, user: User, branch_id: int | None) -> Branch:
    if branch_id is None:
        return default_branch_for_user(db, user)
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Seller/GST profile does not exist",
        )
    ensure_branch_access(user, branch.id)
    return branch
