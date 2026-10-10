from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import ensure_branch_access, get_current_active_user, require_roles
from app.db.session import get_db
from app.models.company import Branch, Company
from app.models.enums import UserRole
from app.models.user import User, UserBranchAssignment
from app.schemas.branch import BranchCreate, BranchRead, BranchUpdate
from app.services.account_security import audit, snapshot


router = APIRouter()


def _get_company_or_422(db: Session, company_id: int) -> None:
    if db.get(Company, company_id) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Company does not exist",
        )


def _ensure_gstin_is_unique(db: Session, gstin: str, branch_id: int | None = None) -> None:
    statement = select(Branch.id).where(Branch.gstin == gstin)
    if branch_id is not None:
        statement = statement.where(Branch.id != branch_id)
    if db.scalar(statement) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="GSTIN already exists")


@router.post("", response_model=BranchRead, status_code=status.HTTP_201_CREATED)
def create_branch(
    request: BranchCreate,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> Branch:
    _get_company_or_422(db, request.company_id)
    _ensure_gstin_is_unique(db, request.gstin)
    branch = Branch(**request.model_dump())
    db.add(branch)
    db.flush()
    audit(db,actor,"seller_gst_profile_created","seller_profile",branch.id,after=snapshot(branch))
    db.commit()
    db.refresh(branch)
    return branch


@router.get("", response_model=list[BranchRead])
def list_branches(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[Branch]:
    statement = select(Branch).order_by(Branch.id)
    if current_user.role != UserRole.ADMIN:
        statement = statement.join(UserBranchAssignment).where(
            UserBranchAssignment.user_id == current_user.id
        )
    return list(db.scalars(statement))


@router.get("/{branch_id}", response_model=BranchRead)
def get_branch(
    branch_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Branch:
    branch = db.get(Branch, branch_id)
    if branch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller/GST profile not found")
    ensure_branch_access(current_user, branch_id)
    return branch


@router.patch("/{branch_id}", response_model=BranchRead)
def update_branch(
    branch_id: int,
    request: BranchUpdate,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> Branch:
    branch = db.scalar(select(Branch).where(Branch.id==branch_id).with_for_update().execution_options(populate_existing=True))
    if branch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller/GST profile not found")
    before=snapshot(branch)
    updates = request.model_dump(exclude_unset=True)
    if "company_id" in updates:
        _get_company_or_422(db, updates["company_id"])
    if "gstin" in updates:
        _ensure_gstin_is_unique(db, updates["gstin"], branch.id)
    for field, value in updates.items():
        setattr(branch, field, value)
    db.flush()
    audit(db,actor,"seller_gst_profile_updated","seller_profile",branch.id,before=before,after=snapshot(branch))
    db.commit()
    db.refresh(branch)
    return branch
