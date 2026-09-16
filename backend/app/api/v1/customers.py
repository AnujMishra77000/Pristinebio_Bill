from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, resolve_branch_for_user
from app.db.session import get_db
from app.models.company import Branch
from app.models.enums import UserRole
from app.models.master_records import Customer
from app.models.user import User
from app.schemas.common import AddressRead
from app.schemas.master_records import CustomerCreate, CustomerRead, CustomerUpdate


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
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> CustomerRead:
    branch = resolve_branch_for_user(db, current_user, request.branch_id)
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
    return [_customer_read(customer) for customer in db.scalars(statement)]


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
    for field, value in updates.items():
        setattr(customer, field, value)
    if request.billing_address is not None:
        for field, value in _address_values("billing", request.billing_address.model_dump()).items():
            setattr(customer, field, value)
    if request.shipping_address is not None:
        for field, value in _address_values("shipping", request.shipping_address.model_dump()).items():
            setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return _customer_read(customer)
