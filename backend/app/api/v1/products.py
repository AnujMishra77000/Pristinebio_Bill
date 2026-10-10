from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, resolve_branch_for_user
from app.db.session import get_db
from app.models.company import Branch
from app.models.enums import UserRole
from app.models.master_records import Manufacturer, Product
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


def _validate_manufacturer(db: Session, branch_id: int, manufacturer_id: int | None, product_code: str | None) -> None:
    if manufacturer_id is None:
        if product_code:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="A manufacturer is required when a manufacturer product code is supplied")
        return
    manufacturer = db.get(Manufacturer, manufacturer_id)
    if manufacturer is None or manufacturer.branch_id != branch_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Manufacturer does not exist for this seller profile")
    if not manufacturer.is_active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Manufacturer is inactive")


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(
    request: ProductCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Product:
    branch = resolve_branch_for_user(db, current_user, request.branch_id)
    values = request.model_dump()
    values["branch_id"] = branch.id
    _validate_manufacturer(db, branch.id, values["manufacturer_id"], values["manufacturer_product_code"])
    product = Product(**values)
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This manufacturer product code is already in use") from None
    db.refresh(product)
    return product


@router.get("", response_model=list[ProductRead])
def list_products(
    branch_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[Product]:
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
    statement = select(Product).options(selectinload(Product.manufacturer)).order_by(Product.id)
    if branch_id is not None:
        statement = statement.where(Product.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        statement = statement.where(Product.branch_id.in_(assigned_branch_ids(current_user)))
    return list(db.scalars(statement.limit(limit)))


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
    target_branch_id = updates.get("branch_id", product.branch_id)
    target_manufacturer_id = updates.get("manufacturer_id", product.manufacturer_id)
    target_product_code = updates.get("manufacturer_product_code", product.manufacturer_product_code)
    manufacturer_link_changed = (
        target_branch_id != product.branch_id
        or target_manufacturer_id != product.manufacturer_id
        or target_product_code != product.manufacturer_product_code
    )
    if manufacturer_link_changed or updates.get("is_active") is True:
        _validate_manufacturer(db, target_branch_id, target_manufacturer_id, target_product_code)
    for field, value in updates.items():
        setattr(product, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This manufacturer product code is already in use") from None
    db.refresh(product)
    return product
