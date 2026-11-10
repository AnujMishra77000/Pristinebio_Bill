from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user, require_roles
from app.services.account_security import audit, snapshot
from app.db.session import get_db
from app.models.company import Branch
from app.models.enums import UserRole
from app.models.master_records import BankAccount
from app.models.user import User
from app.schemas.master_records import BankAccountCreate, BankAccountRead, BankAccountUpdate


router = APIRouter()


def _lock_profiles(db: Session, branch_ids: set[int]) -> None:
    # All bank writes take profile locks first, in ID order. This also
    # serializes concurrent default selections without changing the schema.
    profiles = list(db.scalars(
        select(Branch).where(Branch.id.in_(branch_ids)).order_by(Branch.id).with_for_update()
    ))
    if len(profiles) != len(branch_ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Branch does not exist")


def _ensure_default_is_active(is_active: bool, is_default: bool) -> None:
    if is_default and not is_active:
        raise HTTPException(status_code=422, detail={
            "field": "is_default", "message": "Only active bank accounts can be set as default",
        })


def _clear_other_defaults(db: Session, actor: User, branch_id: int, except_id: int | None = None) -> None:
    statement = select(BankAccount).where(
        BankAccount.branch_id == branch_id, BankAccount.is_default.is_(True),
    ).order_by(BankAccount.id).with_for_update().execution_options(populate_existing=True)
    if except_id is not None:
        statement = statement.where(BankAccount.id != except_id)
    for account in db.scalars(statement):
        before = snapshot(account)
        account.is_default = False
        db.flush()
        audit(db, actor, "bank_account_updated", "bank_account", account.id,
              before=before, after=snapshot(account))


def _get_bank_account(db: Session, current_user: User, bank_account_id: int) -> BankAccount:
    bank_account = db.scalar(select(BankAccount).where(BankAccount.id==bank_account_id).execution_options(populate_existing=True))
    if bank_account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank account not found")
    ensure_branch_access(current_user, bank_account.branch_id)
    return bank_account


@router.post("", response_model=BankAccountRead, status_code=status.HTTP_201_CREATED)
def create_bank_account(
    request: BankAccountCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> BankAccount:
    ensure_branch_access(current_user, request.branch_id)
    _ensure_default_is_active(request.is_active, request.is_default)
    _lock_profiles(db, {request.branch_id})
    if request.is_default:
        _clear_other_defaults(db, current_user, request.branch_id)
    bank_account = BankAccount(**request.model_dump())
    db.add(bank_account)
    db.flush()
    audit(db,current_user,"bank_account_created","bank_account",bank_account.id,after=snapshot(bank_account))
    db.commit()
    db.refresh(bank_account)
    return bank_account


@router.get("", response_model=list[BankAccountRead])
def list_bank_accounts(
    branch_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[BankAccount]:
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
    statement = select(BankAccount).order_by(BankAccount.id)
    if branch_id is not None:
        statement = statement.where(BankAccount.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        statement = statement.where(BankAccount.branch_id.in_(assigned_branch_ids(current_user)))
    return list(db.scalars(statement.limit(limit)))


@router.get("/{bank_account_id}", response_model=BankAccountRead)
def get_bank_account(
    bank_account_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> BankAccount:
    return _get_bank_account(db, current_user, bank_account_id)


@router.patch("/{bank_account_id}", response_model=BankAccountRead)
def update_bank_account(
    bank_account_id: int,
    request: BankAccountUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> BankAccount:
    bank_account = _get_bank_account(db, current_user, bank_account_id)
    original_branch_id = bank_account.branch_id
    updates = request.model_dump(exclude_unset=True)
    target_branch_id = updates.get("branch_id", original_branch_id)
    if target_branch_id is None:
        raise HTTPException(status_code=422, detail="Seller/GST profile cannot be null")
    ensure_branch_access(current_user, target_branch_id)
    _lock_profiles(db, {original_branch_id, target_branch_id})
    bank_account = db.scalar(select(BankAccount).where(BankAccount.id==bank_account_id).with_for_update().execution_options(populate_existing=True))
    if bank_account.branch_id != original_branch_id:
        raise HTTPException(status_code=409, detail="Bank account seller profile changed. Reload before saving.")
    before=snapshot(bank_account)
    target_active = updates.get("is_active", bank_account.is_active)
    target_default = updates.get("is_default", bank_account.is_default)
    if not target_active and "is_default" not in updates:
        updates["is_default"] = target_default = False
    _ensure_default_is_active(target_active, target_default)
    if target_default:
        _clear_other_defaults(db, current_user, target_branch_id, except_id=bank_account_id)
    for field, value in updates.items():
        setattr(bank_account, field, value)
    db.flush()
    audit(db,current_user,"bank_account_updated","bank_account",bank_account.id,before=before,after=snapshot(bank_account))
    db.commit()
    db.refresh(bank_account)
    return bank_account
