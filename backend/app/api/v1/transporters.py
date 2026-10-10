from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import assigned_branch_ids, ensure_branch_access, get_current_active_user
from app.db.session import get_db
from app.models.company import Branch
from app.models.enums import UserRole
from app.models.master_records import Transporter
from app.models.user import User
from app.schemas.master_records import TransporterCreate, TransporterRead, TransporterUpdate


router = APIRouter()


def _ensure_branch_exists(db: Session, branch_id: int) -> None:
    if db.get(Branch, branch_id) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Branch does not exist")


def _get_transporter(db: Session, current_user: User, transporter_id: int) -> Transporter:
    transporter = db.get(Transporter, transporter_id)
    if transporter is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transporter not found")
    ensure_branch_access(current_user, transporter.branch_id)
    return transporter


@router.post("", response_model=TransporterRead, status_code=status.HTTP_201_CREATED)
def create_transporter(
    request: TransporterCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Transporter:
    ensure_branch_access(current_user, request.branch_id)
    _ensure_branch_exists(db, request.branch_id)
    transporter = Transporter(**request.model_dump())
    db.add(transporter)
    db.commit()
    db.refresh(transporter)
    return transporter


@router.get("", response_model=list[TransporterRead])
def list_transporters(
    branch_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[Transporter]:
    if branch_id is not None:
        ensure_branch_access(current_user, branch_id)
    statement = select(Transporter).order_by(Transporter.id)
    if branch_id is not None:
        statement = statement.where(Transporter.branch_id == branch_id)
    elif current_user.role != UserRole.ADMIN:
        statement = statement.where(Transporter.branch_id.in_(assigned_branch_ids(current_user)))
    return list(db.scalars(statement.limit(limit)))


@router.get("/{transporter_id}", response_model=TransporterRead)
def get_transporter(
    transporter_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Transporter:
    return _get_transporter(db, current_user, transporter_id)


@router.patch("/{transporter_id}", response_model=TransporterRead)
def update_transporter(
    transporter_id: int,
    request: TransporterUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Transporter:
    transporter = _get_transporter(db, current_user, transporter_id)
    updates = request.model_dump(exclude_unset=True)
    if "branch_id" in updates:
        ensure_branch_access(current_user, updates["branch_id"])
        _ensure_branch_exists(db, updates["branch_id"])
    for field, value in updates.items():
        setattr(transporter, field, value)
    db.commit()
    db.refresh(transporter)
    return transporter
