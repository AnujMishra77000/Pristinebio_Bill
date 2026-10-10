from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_active_user, require_roles
from app.db.session import get_db
from app.models.company import Branch, Company
from app.models.enums import UserRole
from app.models.user import User, UserBranchAssignment
from app.schemas.company import CompanyCreate, CompanyRead, CompanyUpdate, SellerProfileRead, SellerProfileUpsert
from app.services.account_security import audit, snapshot


router = APIRouter()


def _profile_branch_for_user(db: Session, user: User) -> Branch | None:
    """Resolve the one seller profile a user may edit in single-company mode."""
    if user.role == UserRole.ADMIN:
        return db.scalar(select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.id).with_for_update().execution_options(populate_existing=True))

    assigned_branch_ids = {assignment.branch_id for assignment in user.branch_assignments}
    if not assigned_branch_ids:
        if db.scalar(select(Branch.id).where(Branch.is_active.is_(True))) is not None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seller/GST profile access denied")
        return None

    branch = db.scalar(
        select(Branch)
        .where(Branch.id.in_(assigned_branch_ids), Branch.is_active.is_(True))
        .order_by(Branch.id)
    )
    if branch is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seller/GST profile access denied")
    return branch


def _ensure_profile_gstin_is_unique(db: Session, gstin: str, branch_id: int | None = None) -> None:
    statement = select(Branch.id).where(Branch.gstin == gstin)
    if branch_id is not None:
        statement = statement.where(Branch.id != branch_id)
    if db.scalar(statement) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="GSTIN already exists")


def _profile_response(company: Company | None, branch: Branch | None) -> SellerProfileRead:
    return SellerProfileRead(company=company, seller_profile=branch)


@router.get("/profile", response_model=SellerProfileRead)
def get_seller_profile(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> SellerProfileRead:
    branch = _profile_branch_for_user(db, current_user)
    company = db.get(Company, branch.company_id) if branch else db.scalar(
        select(Company).where(Company.is_active.is_(True)).order_by(Company.id)
    )
    return _profile_response(company, branch)


@router.put("/profile", response_model=SellerProfileRead)
def upsert_seller_profile(
    request: SellerProfileUpsert,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> SellerProfileRead:
    branch = _profile_branch_for_user(db, current_user)
    company = db.get(Company, branch.company_id) if branch else db.scalar(
        select(Company).where(Company.is_active.is_(True)).order_by(Company.id)
    )
    if company is not None:
        company=db.scalar(select(Company).where(Company.id==company.id).with_for_update().execution_options(populate_existing=True))

    before = {"company":snapshot(company) if company else None,"seller_profile":snapshot(branch) if branch else None}

    if branch is not None:
        _ensure_profile_gstin_is_unique(db, request.gstin, branch.id)
    else:
        active_branch_exists = db.scalar(select(Branch.id).where(Branch.is_active.is_(True))) is not None
        if active_branch_exists:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Seller/GST profile access denied")
        _ensure_profile_gstin_is_unique(db, request.gstin)

    if company is None:
        company = Company()
        db.add(company)

    company.legal_name = request.legal_name
    company.trade_name = request.trade_name
    company.pan = request.pan
    company.registered_address = request.registered_address
    company.logo_data_uri = request.logo_data_uri
    company.is_active = True
    db.flush()

    if branch is None:
        branch = Branch(
            company_id=company.id,
            name=request.seller_name,
            gstin=request.gstin,
            address_line1=request.address_line1,
            address_line2=request.address_line2,
            city=request.city,
            state=request.state,
            state_code=request.state_code,
            postal_code=request.postal_code,
            phone=request.phone,
            email=request.email,
            secondary_email=request.secondary_email,
            bank_name=request.bank_name,
            bank_branch_name=request.bank_branch_name,
            bank_account_name=request.bank_account_name,
            bank_account_number=request.bank_account_number,
            bank_ifsc_code=request.bank_ifsc_code,
            terms_body=request.terms_body,
            is_active=request.is_active,
        )
        db.add(branch)
        db.flush()
        if current_user.role != UserRole.ADMIN:
            db.add(UserBranchAssignment(user_id=current_user.id, branch_id=branch.id))
    else:
        branch.name = request.seller_name
        branch.gstin = request.gstin
        branch.address_line1 = request.address_line1
        branch.address_line2 = request.address_line2
        branch.city = request.city
        branch.state = request.state
        branch.state_code = request.state_code
        branch.postal_code = request.postal_code
        branch.phone = request.phone
        branch.email = request.email
        if "secondary_email" in request.model_fields_set:
            branch.secondary_email = request.secondary_email
        branch.bank_name = request.bank_name
        branch.bank_branch_name = request.bank_branch_name
        branch.bank_account_name = request.bank_account_name
        branch.bank_account_number = request.bank_account_number
        branch.bank_ifsc_code = request.bank_ifsc_code
        branch.terms_body = request.terms_body
        branch.is_active = request.is_active

    db.flush()
    audit(db,current_user,"seller_profile_updated","seller_profile",branch.id,before=before,after={"company":snapshot(company),"seller_profile":snapshot(branch)})
    db.commit()
    db.refresh(company)
    db.refresh(branch)
    return _profile_response(company, branch)


def _ensure_company_access(db: Session, user: User, company_id: int) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    if user.role == UserRole.ADMIN:
        return company

    assignment = db.scalar(
        select(UserBranchAssignment.id)
        .join(Branch, Branch.id == UserBranchAssignment.branch_id)
        .where(
            UserBranchAssignment.user_id == user.id,
            Branch.company_id == company_id,
        )
    )
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Company access denied")
    return company


@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(
    request: CompanyCreate,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> Company:
    company = Company(**request.model_dump())
    db.add(company)
    db.flush()
    audit(db,actor,"company_created","company",company.id,after=snapshot(company))
    db.commit()
    db.refresh(company)
    return company


@router.get("", response_model=list[CompanyRead])
def list_companies(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> list[Company]:
    statement = select(Company).order_by(Company.id)
    if current_user.role != UserRole.ADMIN:
        statement = (
            statement.join(Branch)
            .join(UserBranchAssignment)
            .where(UserBranchAssignment.user_id == current_user.id)
            .distinct()
        )
    return list(db.scalars(statement))


@router.get("/{company_id}", response_model=CompanyRead)
def get_company(
    company_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> Company:
    return _ensure_company_access(db, current_user, company_id)


@router.patch("/{company_id}", response_model=CompanyRead)
def update_company(
    company_id: int,
    request: CompanyUpdate,
    db: Annotated[Session, Depends(get_db)],
    actor: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
) -> Company:
    company = db.scalar(select(Company).where(Company.id==company_id).with_for_update().execution_options(populate_existing=True))
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    before=snapshot(company)
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    db.flush()
    audit(db,actor,"company_updated","company",company.id,before=before,after=snapshot(company))
    db.commit()
    db.refresh(company)
    return company
