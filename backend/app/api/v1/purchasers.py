"""Purchaser company master APIs used by purchase orders."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, resolve_branch_for_user
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.master_records import Purchaser
from app.models.user import User
from app.schemas.common import AddressRead
from app.schemas.master_records import PurchaserCreate, PurchaserRead, PurchaserUpdate


router = APIRouter()


def _purchaser_address(purchaser: Purchaser) -> AddressRead:
    return AddressRead(
        name=purchaser.address_name,
        address_line1=purchaser.address_line1,
        address_line2=purchaser.address_line2,
        city=purchaser.city,
        state=purchaser.state,
        state_code=purchaser.state_code,
        postal_code=purchaser.postal_code,
    )


def purchaser_read(purchaser: Purchaser) -> PurchaserRead:
    return PurchaserRead(
        id=purchaser.id,
        branch_id=purchaser.branch_id,
        name=purchaser.name,
        gstin=purchaser.gstin,
        pan=purchaser.pan,
        email=purchaser.email,
        phone=purchaser.phone,
        address=_purchaser_address(purchaser),
        is_active=purchaser.is_active,
    )


def purchaser_values(request: PurchaserCreate | PurchaserUpdate) -> dict:
    values = request.model_dump(exclude_unset=True, exclude={"address"})
    if request.address is not None:
        address = request.address.model_dump()
        values.update(
            {
                "address_name": address["name"],
                "address_line1": address["address_line1"],
                "address_line2": address["address_line2"],
                "city": address["city"],
                "state": address["state"],
                "state_code": address["state_code"],
                "postal_code": address["postal_code"],
            }
        )
    return values


def get_purchaser_for_user(db: Session, current_user: User, purchaser_id: int) -> Purchaser:
    purchaser = db.get(Purchaser, purchaser_id)
    if purchaser is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchaser not found")
    ensure_branch_access(current_user, purchaser.branch_id)
    return purchaser


def _raise_duplicate_if_present(db: Session, branch_id: int, request: PurchaserCreate) -> None:
    name_and_phone = and_(
        func.lower(Purchaser.name) == request.name.strip().lower(),
        Purchaser.phone == request.phone,
    )
    identity_match = select(Purchaser).where(Purchaser.branch_id == branch_id)
    identity_match = identity_match.where(or_(name_and_phone, Purchaser.gstin == request.gstin) if request.gstin else name_and_phone)
    if db.scalar(identity_match.limit(1)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A purchaser with the same GSTIN or contact identity already exists")


@router.post("", response_model=PurchaserRead, status_code=status.HTTP_201_CREATED)
def create_purchaser(
    request: PurchaserCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PurchaserRead:
    branch = resolve_branch_for_user(db, current_user, request.branch_id)
    _raise_duplicate_if_present(db, branch.id, request)
    values = purchaser_values(request)
    values["branch_id"] = branch.id
    purchaser = Purchaser(**values)
    db.add(purchaser)
    db.commit()
    db.refresh(purchaser)
    return purchaser_read(purchaser)


@router.get("", response_model=list[PurchaserRead])
def list_purchasers(
    branch_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[PurchaserRead]:
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
    statement = select(Purchaser).order_by(Purchaser.id)
    if branch_id is not None:
        statement = statement.where(Purchaser.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(current_user)
        statement = statement.where(Purchaser.branch_id.in_(assigned) if assigned else false())
    return [purchaser_read(purchaser) for purchaser in db.scalars(statement.limit(limit))]


@router.get("/{purchaser_id}", response_model=PurchaserRead)
def get_purchaser(
    purchaser_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PurchaserRead:
    return purchaser_read(get_purchaser_for_user(db, current_user, purchaser_id))


@router.patch("/{purchaser_id}", response_model=PurchaserRead)
def update_purchaser(
    purchaser_id: int,
    request: PurchaserUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> PurchaserRead:
    purchaser = get_purchaser_for_user(db, current_user, purchaser_id)
    updates = purchaser_values(request)
    if "branch_id" in updates:
        branch = resolve_branch_for_user(db, current_user, updates["branch_id"])
        updates["branch_id"] = branch.id
    for field, value in updates.items():
        setattr(purchaser, field, value)
    db.commit()
    db.refresh(purchaser)
    return purchaser_read(purchaser)
