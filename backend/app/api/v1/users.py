from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_active_user, require_roles
from app.core.security import hash_password
from app.db.session import get_db
from app.models.company import Branch
from app.models.enums import UserRole
from app.models.user import User, UserBranchAssignment
from app.schemas.user import UserCreate, UserRead, UserUpdate


router = APIRouter()


def _user_read(db: Session, user: User) -> UserRead:
    branch_ids = list(
        db.scalars(
            select(UserBranchAssignment.branch_id).where(
                UserBranchAssignment.user_id == user.id
            )
        )
    )
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        branch_ids=branch_ids,
        is_active=user.is_active,
    )


def _validate_branch_ids(db: Session, branch_ids: list[int]) -> None:
    if len(set(branch_ids)) != len(branch_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Branch IDs must be unique",
        )
    found_ids = set(db.scalars(select(Branch.id).where(Branch.id.in_(branch_ids))))
    if found_ids != set(branch_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="One or more branch IDs do not exist",
        )


def _replace_branch_assignments(db: Session, user: User, branch_ids: list[int]) -> None:
    db.query(UserBranchAssignment).filter(
        UserBranchAssignment.user_id == user.id
    ).delete(synchronize_session=False)
    db.add_all(
        [UserBranchAssignment(user_id=user.id, branch_id=branch_id) for branch_id in branch_ids]
    )


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    request: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> UserRead:
    email = str(request.email).strip().lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
    _validate_branch_ids(db, request.branch_ids)

    user = User(
        email=email,
        full_name=request.full_name,
        role=request.role,
        hashed_password=hash_password(request.password),
        is_active=request.is_active,
    )
    db.add(user)
    db.flush()
    _replace_branch_assignments(db, user, request.branch_ids)
    db.commit()
    db.refresh(user)
    return _user_read(db, user)


@router.get("", response_model=list[UserRead])
def list_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> list[UserRead]:
    return [_user_read(db, user) for user in db.scalars(select(User).order_by(User.id))]


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserRead:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if current_user.role != UserRole.ADMIN and current_user.id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return _user_read(db, user)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    request: UserUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> UserRead:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if request.email is not None:
        email = str(request.email).strip().lower()
        duplicate = db.scalar(select(User.id).where(User.email == email, User.id != user.id))
        if duplicate is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
        user.email = email
    if request.full_name is not None:
        user.full_name = request.full_name
    if request.password is not None:
        user.hashed_password = hash_password(request.password)
    if request.role is not None:
        user.role = request.role
    if request.is_active is not None:
        user.is_active = request.is_active
    if request.branch_ids is not None:
        _validate_branch_ids(db, request.branch_ids)
        _replace_branch_assignments(db, user, request.branch_ids)

    db.commit()
    db.refresh(user)
    return _user_read(db, user)
