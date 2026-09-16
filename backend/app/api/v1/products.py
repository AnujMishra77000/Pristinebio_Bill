from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, resolve_branch_for_user
from app.db.session import get_db
from app.models.company import Branch
from app.models.enums import UserRole
from app.models.master_records import Product
from app.models.user import User
from app.schemas.master_records import ProductCreate, ProductRead, ProductUpdate


router = APIRouter()


def _ensure_branch_exists(db: Session, branch_id: int) -> None:
    if db.get(Branch, branch_id) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Branch does not exist")


def _get_product(db: Session, current_user: User, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    ensure_branch_access(current_user, product.branch_id)
    return product


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    request: ProductCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Product:
    branch = resolve_branch_for_user(db, current_user, request.branch_id)
    values = request.model_dump()
    values["branch_id"] = branch.id
    product = Product(**values)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("", response_model=list[ProductRead])
def list_products(
    branch_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[Product]:
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
    statement = select(Product).order_by(Product.id)
    if branch_id is not None:
        statement = statement.where(Product.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        statement = statement.where(Product.branch_id.in_(assigned_branch_ids(current_user)))
    return list(db.scalars(statement))


@router.get("/{product_id}", response_model=ProductRead)
def get_product(
    product_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Product:
    return _get_product(db, current_user, product_id)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int,
    request: ProductUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Product:
    product = _get_product(db, current_user, product_id)
    updates = request.model_dump(exclude_unset=True)
    if "branch_id" in updates:
        ensure_branch_access(current_user, updates["branch_id"])
        _ensure_branch_exists(db, updates["branch_id"])
    for field, value in updates.items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product
