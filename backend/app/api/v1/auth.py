from typing import Annotated
from secrets import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_active_user
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User, UserBranchAssignment
from app.schemas.auth import LoginRequest, RefreshTokenRequest, RegistrationRequest, TokenResponse
from app.models.enums import UserRole
from app.schemas.user import AdminBootstrapCreate, CurrentUserResponse, UserRead


router = APIRouter()


_BOOTSTRAP_LOCK_KEY = 5_273_476_181


def _lock_bootstrap_transaction(db: Session) -> None:
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _BOOTSTRAP_LOCK_KEY},
        )


def _current_user_response(db: Session, user: User) -> CurrentUserResponse:
    branch_ids = list(
        db.scalars(
            select(UserBranchAssignment.branch_id).where(
                UserBranchAssignment.user_id == user.id
            )
        )
    )
    return CurrentUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        branch_ids=branch_ids,
    )


def _invalid_credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/bootstrap-admin", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def bootstrap_admin(
    request: AdminBootstrapCreate,
    db: Annotated[Session, Depends(get_db)],
    setup_token: Annotated[str | None, Header(alias="X-Setup-Token")] = None,
) -> UserRead:
    _lock_bootstrap_transaction(db)
    if db.scalar(select(User.id).limit(1)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Admin bootstrap is no longer available",
        )

    settings = get_settings()
    if not settings.admin_bootstrap_token or setup_token != settings.admin_bootstrap_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid setup token",
        )

    user = User(
        email=str(request.email).strip().lower(),
        full_name=request.full_name,
        role=UserRole.ADMIN,
        hashed_password=hash_password(request.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        branch_ids=[],
        is_active=user.is_active,
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(
    request: RegistrationRequest,
    db: Annotated[Session, Depends(get_db)],
) -> UserRead:
    settings = get_settings()
    configured_master_password = settings.admin_registration_master_password
    if not configured_master_password or not compare_digest(
        request.master_password,
        configured_master_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid master password",
        )

    email = str(request.email).strip().lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")

    user = User(
        email=email,
        full_name=request.full_name,
        role=UserRole.ADMIN,
        hashed_password=hash_password(request.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        branch_ids=[],
        is_active=user.is_active,
    )


@router.post("/login", response_model=TokenResponse, response_model_exclude_none=True)
def login(
    request: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    email = str(request.email).strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(request.password, user.hashed_password):
        raise _invalid_credentials_exception()
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account pending admin approval",
        )

    return TokenResponse(
        access_token=create_access_token(subject=str(user.id), role=user.role),
        refresh_token=create_refresh_token(subject=str(user.id), role=user.role),
        user=_current_user_response(db, user),
    )


@router.post("/refresh", response_model=TokenResponse, response_model_exclude_none=True)
def refresh(
    request: RefreshTokenRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    try:
        payload = decode_token(request.refresh_token, expected_type="refresh")
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise _invalid_credentials_exception() from None

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _invalid_credentials_exception()

    return TokenResponse(
        access_token=create_access_token(subject=str(user.id), role=user.role),
    )


@router.get("/me", response_model=CurrentUserResponse)
def read_current_user(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CurrentUserResponse:
    return _current_user_response(db, current_user)
