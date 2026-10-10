from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, resolve_branch_for_user
from app.db.session import get_db
from app.models.company import Branch
from app.models.enums import UserRole
from app.models.master_records import Customer
from app.models.user import User
from app.schemas.common import AddressPayload, AddressRead
from app.schemas.master_records import CustomerCreate, CustomerRead, CustomerUpdate
from app.services.customer_identity import find_customer_by_gstin, lock_customer_gstin, normalize_gstin, require_active_customer


router = APIRouter()


def _ensure_branch_exists(db: Session, branch_id: int) -> None:
    if db.get(Branch, branch_id) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Branch does not exist")


def _address(customer: Customer, prefix: str) -> AddressRead | None:
    address_line1 = getattr(customer, f"{prefix}_address_line1")
    if address_line1 is None:
        return None
    return AddressRead(
        name=getattr(customer, f"{prefix}_name"),
        address_line1=address_line1,
        address_line2=getattr(customer, f"{prefix}_address_line2"),
        city=getattr(customer, f"{prefix}_city"),
        state=getattr(customer, f"{prefix}_state"),
        state_code=getattr(customer, f"{prefix}_state_code"),
        postal_code=getattr(customer, f"{prefix}_postal_code"),
    )


def _customer_read(customer: Customer) -> CustomerRead:
    return CustomerRead(
        id=customer.id,
        branch_id=customer.branch_id,
        name=customer.name,
        gstin=customer.gstin,
        pan=customer.pan,
        email=customer.email,
        phone=customer.phone,
        billing_address=_address(customer, "billing"),
        shipping_address=_address(customer, "shipping"),
        is_active=customer.is_active,
    )


def _address_values(prefix: str, address: dict | None) -> dict[str, str | None]:
    if address is None:
        return {}
    return {f"{prefix}_{field}": value for field, value in address.items()}


def _get_customer(db: Session, current_user: User, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    ensure_branch_access(current_user, customer.branch_id)
    return customer


@router.post("", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(
    request: CustomerCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CustomerRead:
    branch = resolve_branch_for_user(db, current_user, request.branch_id)
    lock_customer_gstin(db, branch.id, request.gstin)
    existing = find_customer_by_gstin(db, branch.id, request.gstin)
    if existing is not None:
        require_active_customer(existing)
        response.status_code = status.HTTP_200_OK
        # Creation is not a master edit. Preserve the saved identity/address.
        db.commit()
        return _customer_read(existing)
    values = request.model_dump(exclude={"billing_address", "shipping_address"})
    values["branch_id"] = branch.id
    values.update(_address_values("billing", request.billing_address.model_dump()))
    values.update(_address_values("shipping", request.shipping_address.model_dump() if request.shipping_address else None))
    customer = Customer(**values)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return _customer_read(customer)


@router.get("", response_model=list[CustomerRead])
def list_customers(
    branch_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    billing: bool = False,
    register: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[CustomerRead]:
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
    statement = select(Customer).order_by(Customer.id)
    if branch_id is not None:
        statement = statement.where(Customer.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        statement = statement.where(Customer.branch_id.in_(assigned_branch_ids(current_user)))
    if billing or register:
        older = aliased(Customer)
        gstin = func.nullif(func.upper(func.trim(Customer.gstin)), "")
        preferred_match = older.id < Customer.id
        if register and not billing:
            # One visible identity, preferring an active record, otherwise the
            # oldest inactive one. Historical IDs remain available by detail.
            preferred_match = or_(
                and_(older.is_active.is_(True), Customer.is_active.is_(False)),
                and_(older.is_active == Customer.is_active, older.id < Customer.id),
            )
        earlier_active_match = select(older.id).where(
            older.branch_id == Customer.branch_id,
            func.upper(func.trim(older.gstin)) == gstin,
            preferred_match,
            *([older.is_active.is_(True)] if billing else []),
        ).exists()
        # Filter BEFORE the limit; no-GSTIN buyers remain independent records.
        statement = statement.where(or_(gstin.is_(None), ~earlier_active_match))
        if billing:
            statement = statement.where(Customer.is_active.is_(True))
    return [_customer_read(customer) for customer in db.scalars(statement.offset(offset).limit(limit))]


@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(
    customer_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CustomerRead:
    return _customer_read(_get_customer(db, current_user, customer_id))


@router.patch("/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: int,
    request: CustomerUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CustomerRead:
    customer = _get_customer(db, current_user, customer_id)
    updates = request.model_dump(exclude_unset=True, exclude={"billing_address", "shipping_address"})
    if "branch_id" in updates:
        ensure_branch_access(current_user, updates["branch_id"])
        _ensure_branch_exists(db, updates["branch_id"])
    target_branch = updates.get("branch_id", customer.branch_id)
    target_gstin = normalize_gstin(updates.get("gstin", customer.gstin))
    identity_changed = (target_branch, target_gstin) != (customer.branch_id, normalize_gstin(customer.gstin))
    reactivating = updates.get("is_active") is True and not customer.is_active
    if identity_changed or reactivating:
        lock_customer_gstin(db, target_branch, target_gstin)
        if find_customer_by_gstin(db, target_branch, target_gstin, exclude_id=customer.id) is not None:
            raise HTTPException(status_code=409, detail={"field": "gstin", "message": "This GSTIN already belongs to a saved customer. Edit that customer instead."})
    for field, value in updates.items():
        setattr(customer, field, value)
    if request.billing_address is not None:
        for field, value in _address_values("billing", request.billing_address.model_dump()).items():
            setattr(customer, field, value)
    if "shipping_address" in request.model_fields_set:
        address = request.shipping_address.model_dump() if request.shipping_address is not None else {field: None for field in AddressPayload.model_fields}
        for field, value in _address_values("shipping", address).items():
            setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return _customer_read(customer)
