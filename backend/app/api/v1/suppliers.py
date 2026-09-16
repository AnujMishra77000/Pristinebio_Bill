from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, resolve_branch_for_user
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.master_records import Supplier
from app.models.user import User
from app.schemas.common import AddressRead
from app.schemas.master_records import SupplierCreate, SupplierRead, SupplierUpdate


router = APIRouter()


def _supplier_address(supplier: Supplier) -> AddressRead:
    return AddressRead(
        name=supplier.address_name,
        address_line1=supplier.address_line1,
        address_line2=supplier.address_line2,
        city=supplier.city,
        state=supplier.state,
        state_code=supplier.state_code,
        postal_code=supplier.postal_code,
    )


def supplier_read(supplier: Supplier) -> SupplierRead:
    return SupplierRead(
        id=supplier.id,
        branch_id=supplier.branch_id,
        name=supplier.name,
        gstin=supplier.gstin,
        pan=supplier.pan,
        email=supplier.email,
        phone=supplier.phone,
        address=_supplier_address(supplier),
        is_active=supplier.is_active,
    )


def supplier_values(request: SupplierCreate | SupplierUpdate) -> dict:
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


def get_supplier_for_user(db: Session, current_user: User, supplier_id: int) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    ensure_branch_access(current_user, supplier.branch_id)
    return supplier


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(
    request: SupplierCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SupplierRead:
    branch = resolve_branch_for_user(db, current_user, request.branch_id)
    values = supplier_values(request)
    values["branch_id"] = branch.id
    supplier = Supplier(**values)
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier_read(supplier)


@router.get("", response_model=list[SupplierRead])
def list_suppliers(
    branch_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[SupplierRead]:
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
    statement = select(Supplier).order_by(Supplier.id)
    if branch_id is not None:
        statement = statement.where(Supplier.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(current_user)
        statement = statement.where(Supplier.branch_id.in_(assigned) if assigned else false())
    return [supplier_read(supplier) for supplier in db.scalars(statement)]


@router.get("/{supplier_id}", response_model=SupplierRead)
def get_supplier(
    supplier_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SupplierRead:
    return supplier_read(get_supplier_for_user(db, current_user, supplier_id))


@router.patch("/{supplier_id}", response_model=SupplierRead)
def update_supplier(
    supplier_id: int,
    request: SupplierUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SupplierRead:
    supplier = get_supplier_for_user(db, current_user, supplier_id)
    updates = supplier_values(request)
    if "branch_id" in updates:
        branch = resolve_branch_for_user(db, current_user, updates["branch_id"])
        updates["branch_id"] = branch.id
    for field, value in updates.items():
        setattr(supplier, field, value)
    db.commit()
    db.refresh(supplier)
    return supplier_read(supplier)
