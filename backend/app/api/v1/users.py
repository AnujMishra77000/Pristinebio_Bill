from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user, require_roles
from app.api.v1.auth import current_user_response, mfa_reauth, validate_assignments
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User, UserBranchAssignment
from app.schemas.user import UserRead, UserUpdate
from app.schemas.auth import MFAReset
from app.services.account_security import admin_lock, audit, lock_current_authority, locked_user, reset_mfa, revoke_user_sessions, throttle

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Admin = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.post("", status_code=410)
def removed_direct_provisioning(user: Admin):
    raise HTTPException(410,"Create an invitation instead of assigning another person's password")


@router.get("", response_model=list[UserRead])
def list_users(db: Db, user: Admin):
    return [current_user_response(db,u) for u in db.scalars(select(User).order_by(User.id))]


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id:int, db:Db, current:Annotated[User,Depends(get_current_active_user)]):
    user=db.get(User,user_id)
    if not user:
        raise HTTPException(404,"User not found")
    if current.role!=UserRole.ADMIN and current.id!=user.id:
        raise HTTPException(403,"Insufficient permissions")
    return current_user_response(db,user)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id:int, data:UserUpdate, db:Db, actor:Admin):
    admin_lock(db)
    user=db.get(User,user_id)
    if not user:
        raise HTTPException(404,"User not found")
    user=locked_user(db,user)
    before=current_user_response(db,user).model_dump(mode="json")
    role=data.role if data.role is not None else user.role
    active=data.is_active if data.is_active is not None else user.is_active
    if user.role==UserRole.ADMIN and user.is_active and (role!=UserRole.ADMIN or not active):
        others=list(db.scalars(select(User.id).where(User.role==UserRole.ADMIN,User.is_active.is_(True),User.id!=user.id).with_for_update()))
        if not others:
            raise HTTPException(409,"The last active administrator cannot be disabled or demoted")
    ids=data.branch_ids if data.branch_ids is not None else before["branch_ids"]
    if data.role is not None or data.branch_ids is not None:
        validate_assignments(db,role,ids)
    if data.email is not None:
        email=str(data.email).lower()
        if db.scalar(select(User.id).where(User.email==email,User.id!=user.id)):
            raise HTTPException(409,"Email already exists")
        user.email=email
    if data.full_name is not None:
        user.full_name=data.full_name
    user.role,user.is_active=role,active
    if data.branch_ids is not None:
        db.query(UserBranchAssignment).filter(UserBranchAssignment.user_id==user.id).delete(synchronize_session=False)
        db.add_all([UserBranchAssignment(user_id=user.id,branch_id=i) for i in ids])
    db.flush()
    after=current_user_response(db,user).model_dump(mode="json")
    if before != after:
        revoke_user_sessions(db,user.id)
        audit(db,actor,"account_updated",entity_id=user.id,before=before,after=after)
    db.commit()
    return current_user_response(db,user)


@router.post("/{user_id}/revoke-sessions")
def revoke_sessions(user_id:int,db:Db,actor:Admin):
    if not db.get(User,user_id):
        raise HTTPException(404,"User not found")
    revoke_user_sessions(db,user_id)
    audit(db,actor,"account_sessions_revoked",entity_id=user_id)
    db.commit()
    return {"detail":"User sessions revoked"}


@router.post("/{user_id}/mfa-reset")
def administrative_mfa_reset(user_id:int,data:MFAReset,request:Request,db:Db,actor:Admin):
    actor=lock_current_authority(db,request,actor,admin=True)
    throttle(db,request,str(actor.id),"mfa")
    if user_id==actor.id:
        raise HTTPException(403,"Use your recovery code for self-recovery; administrators cannot reset their own MFA")
    user=db.get(User,user_id)
    if not user:
        raise HTTPException(404,"User not found")
    admin_lock(db)
    mfa_reauth(data,db,actor)
    user=locked_user(db,user)
    before={"mfa_enabled":user.mfa_enabled_at is not None}
    reset_mfa(db,user)
    audit(db,actor,"mfa_administrative_reset",entity_id=user.id,before=before,after={"mfa_enabled":False,"reason":data.reason})
    db.commit()
    return {"detail":"MFA reset; all sessions revoked and reenrollment required"}
