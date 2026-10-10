from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user
from app.db.session import get_db
from app.models.company import Branch
from app.models.enums import UserRole
from app.models.master_records import TermsAndConditions
from app.models.user import User
from app.schemas.master_records import TermsCreate, TermsRead, TermsUpdate


router = APIRouter()


def _ensure_branch_exists(db: Session, branch_id: int) -> None:
    if db.get(Branch, branch_id) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Branch does not exist")


def _get_terms(db: Session, current_user: User, terms_id: int) -> TermsAndConditions:
    terms = db.get(TermsAndConditions, terms_id)
    if terms is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terms and conditions not found")
    ensure_branch_access(current_user, terms.branch_id)
    return terms


@router.post("", response_model=TermsRead, status_code=status.HTTP_201_CREATED)
def create_terms(
    request: TermsCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> TermsAndConditions:
    ensure_branch_access(current_user, request.branch_id)
    _ensure_branch_exists(db, request.branch_id)
    terms = TermsAndConditions(**request.model_dump())
    db.add(terms)
    db.commit()
    db.refresh(terms)
    return terms


@router.get("", response_model=list[TermsRead])
def list_terms(
    branch_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[TermsAndConditions]:
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
    statement = select(TermsAndConditions).order_by(TermsAndConditions.id)
    if branch_id is not None:
        statement = statement.where(TermsAndConditions.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        statement = statement.where(TermsAndConditions.branch_id.in_(assigned_branch_ids(current_user)))
    return list(db.scalars(statement.limit(limit)))


@router.get("/{terms_id}", response_model=TermsRead)
def get_terms(
    terms_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> TermsAndConditions:
    return _get_terms(db, current_user, terms_id)


@router.patch("/{terms_id}", response_model=TermsRead)
def update_terms(
    terms_id: int,
    request: TermsUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> TermsAndConditions:
    terms = _get_terms(db, current_user, terms_id)
    updates = request.model_dump(exclude_unset=True)
    if "branch_id" in updates:
        ensure_branch_access(current_user, updates["branch_id"])
        _ensure_branch_exists(db, updates["branch_id"])
    for field, value in updates.items():
        setattr(terms, field, value)
    db.commit()
    db.refresh(terms)
    return terms
