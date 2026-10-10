from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, resolve_branch_for_user
from app.db.session import get_db
from app.models.company import Branch
from app.models.enums import UserRole
from app.models.master_records import Manufacturer
from app.models.user import User
from app.schemas.master_records import ManufacturerCreate, ManufacturerRead, ManufacturerUpdate


router = APIRouter()


def _get_manufacturer(db: Session, current_user: User, manufacturer_id: int) -> Manufacturer:
    manufacturer = db.get(Manufacturer, manufacturer_id)
    if manufacturer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Manufacturer not found")
    ensure_branch_access(current_user, manufacturer.branch_id)
    return manufacturer


@router.post("", response_model=ManufacturerRead, status_code=status.HTTP_201_CREATED)
def create_manufacturer(
    request: ManufacturerCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Manufacturer:
    branch = resolve_branch_for_user(db, current_user, request.branch_id)
    manufacturer = Manufacturer(**request.model_dump(exclude={"branch_id"}), branch_id=branch.id)
    db.add(manufacturer)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A manufacturer with this code already exists for the seller profile") from None
    db.refresh(manufacturer)
    return manufacturer


@router.get("", response_model=list[ManufacturerRead])
def list_manufacturers(
    branch_id: int | None = None,
    active_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[Manufacturer]:
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
    statement = select(Manufacturer).order_by(Manufacturer.code, Manufacturer.id)
    if branch_id is not None:
        statement = statement.where(Manufacturer.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        statement = statement.where(Manufacturer.branch_id.in_(assigned_branch_ids(current_user)))
    if active_only:
        statement = statement.where(Manufacturer.is_active.is_(True))
    return list(db.scalars(statement.limit(limit)))


@router.get("/{manufacturer_id}", response_model=ManufacturerRead)
def get_manufacturer(
    manufacturer_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Manufacturer:
    return _get_manufacturer(db, current_user, manufacturer_id)


@router.patch("/{manufacturer_id}", response_model=ManufacturerRead)
def update_manufacturer(
    manufacturer_id: int,
    request: ManufacturerUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Manufacturer:
    manufacturer = _get_manufacturer(db, current_user, manufacturer_id)
    updates = request.model_dump(exclude_unset=True)
    target_branch_id = updates.get("branch_id", manufacturer.branch_id)
    if target_branch_id != manufacturer.branch_id:
        ensure_branch_access(current_user, target_branch_id)
        if db.get(Branch, target_branch_id) is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Seller/GST profile does not exist")
        if manufacturer.products:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A manufacturer linked to products cannot be moved to another seller profile")
    for field, value in updates.items():
        setattr(manufacturer, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A manufacturer with this code already exists for the seller profile") from None
    db.refresh(manufacturer)
    return manufacturer
