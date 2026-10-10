from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import false, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, resolve_branch_for_user
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.master_records import Supplier
from app.models.purchase_order import PurchaseOrder
from app.models.invoice import Invoice, InvoiceRevision
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
        is_default=supplier.is_default,
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


def _clear_branch_default(db: Session, branch_id: int, except_id: int | None = None) -> None:
    statement = select(Supplier).where(Supplier.branch_id == branch_id, Supplier.is_default.is_(True))
    if except_id is not None:
        statement = statement.where(Supplier.id != except_id)
    for supplier in db.scalars(statement):
        supplier.is_default = False


def _ensure_default_is_active(is_active: bool, is_default: bool) -> None:
    if is_default and not is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only active suppliers can be set as default",
        )


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(
    request: SupplierCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SupplierRead:
    branch = resolve_branch_for_user(db, current_user, request.branch_id)
    _ensure_default_is_active(request.is_active, request.is_default)
    values = supplier_values(request)
    values["branch_id"] = branch.id
    if request.is_default:
        _clear_branch_default(db, branch.id)
    supplier = Supplier(**values)
    db.add(supplier)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another supplier is already being set as the default") from exc
    db.refresh(supplier)
    return supplier_read(supplier)


@router.get("", response_model=list[SupplierRead])
def list_suppliers(
    branch_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    search: str | None = Query(None, max_length=255),
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[SupplierRead]:
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
    statement = select(Supplier).order_by(Supplier.id)
    if active_only:
        statement = statement.where(Supplier.is_active.is_(True)).order_by(None).order_by(Supplier.is_default.desc(), Supplier.id)
    if search and search.strip():
        statement = statement.where(Supplier.name.icontains(search.strip(), autoescape=True))
    if branch_id is not None:
        statement = statement.where(Supplier.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        assigned = assigned_branch_ids(current_user)
        statement = statement.where(Supplier.branch_id.in_(assigned) if assigned else false())
    return [supplier_read(supplier) for supplier in db.scalars(statement.limit(limit))]


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
    target_active = updates.get("is_active", supplier.is_active)
    target_default = updates.get("is_default", supplier.is_default)
    if target_active is False:
        updates["is_default"] = False
        target_default = False
    _ensure_default_is_active(target_active, target_default)
    target_branch_id = updates.get("branch_id", supplier.branch_id)
    if "branch_id" in updates:
        branch = resolve_branch_for_user(db, current_user, updates["branch_id"])
        updates["branch_id"] = branch.id
        target_branch_id = branch.id
    if target_default:
        _clear_branch_default(db, target_branch_id, except_id=supplier.id)
    for field, value in updates.items():
        setattr(supplier, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Another supplier is already the default") from exc
    db.refresh(supplier)
    return supplier_read(supplier)


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(
    supplier_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Response:
    supplier = get_supplier_for_user(db, current_user, supplier_id)
    linked_purchase_order = db.scalar(
        select(PurchaseOrder.id)
        .where(PurchaseOrder.supplier_id == supplier.id)
        .limit(1)
    )
    if linked_purchase_order is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Supplier is used by an existing purchase order; deactivate it instead of deleting it",
        )
    if db.scalar(select(Invoice.id).where(Invoice.supplier_id == supplier.id).limit(1)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Supplier is used by an existing invoice; deactivate it instead of deleting it")
    if db.scalar(select(InvoiceRevision.id).where(
        InvoiceRevision.snapshot["seller_addresses"]["supplier_id"].as_integer() == supplier.id,
    ).limit(1)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Supplier is retained in invoice revision history; deactivate it instead of deleting it")
    db.delete(supplier)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Supplier cannot be deleted because it is referenced by existing data") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
