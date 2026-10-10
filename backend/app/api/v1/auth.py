import secrets
import unicodedata
from datetime import timedelta
from typing import Annotated

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_current_active_user, require_roles
from app.core.config import get_settings
from app.core.csrf import issue_csrf
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models.authentication import AccountInvitation, AuthSession, MFARecoveryCode, SecurityAudit
from app.models.company import Branch
from app.models.enums import UserRole
from app.models.user import User, UserBranchAssignment
from app.schemas.auth import (LoginRequest, SessionResponse, PasswordChange, InvitationCreate, InvitationAccept, MFACode, MFAReauthentication)
from app.schemas.user import AdminRegistrationCreate, CurrentUserResponse
from app.services.account_security import (admin_lock, audit, aware, cipher, clear_cookies, digest, lock_current_authority, locked_user, new_session, now, replace_recovery_codes, requires_mfa, reset_mfa, revoke_user_sessions, rotate_refresh, set_cookie, throttle, verify_totp)

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Current = Annotated[User, Depends(get_current_user)]
Active = Annotated[User, Depends(get_current_active_user)]
Admin = Annotated[User, Depends(require_roles(UserRole.ADMIN))]
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def current_user_response(db, user, session=None):
    return CurrentUserResponse(id=user.id, email=user.email, full_name=user.full_name, role=user.role,
        branch_ids=list(db.scalars(select(UserBranchAssignment.branch_id).where(UserBranchAssignment.user_id==user.id))),
        is_active=user.is_active, password_change_required=user.password_policy_version < 1,
        mfa_enabled=False, mfa_required=False, mfa_verified=True)


def result(db, user, session):
    return SessionResponse(user=current_user_response(db, user, session))


def auth_failure(db, user=None, action="authentication_failed", detail="Unable to sign in with the provided credentials"):
    audit(db, user, action)
    db.commit()
    raise HTTPException(401, detail)


def password_matches(user, password):
    if user.password_policy_version >= 1:
        password = unicodedata.normalize("NFC", password)
    return verify_password(password, user.hashed_password)


@router.get("/csrf")
def csrf(request: Request, response: Response):
    token=issue_csrf(request)
    set_cookie(response, "csrf", token, 3600)
    return {"csrf_token":token}


@router.post("/register", response_model=SessionResponse, status_code=201)
def register_admin(request_data: AdminRegistrationCreate, request: Request, response: Response, db: Db):
    admin_lock(db)
    email = str(request_data.email).lower()
    throttle(db, request, email, "registration")
    if db.scalar(select(User.id).where(User.email == email)):
        audit(db, None, "admin_registration_conflict", after={"email": email})
        db.commit()
        raise HTTPException(409, "An account with this email already exists")
    user=User(email=str(request_data.email).lower(), full_name=request_data.full_name, role=UserRole.ADMIN,
        hashed_password=hash_password(request_data.password), password_policy_version=1, is_active=True)
    db.add(user)
    db.flush()
    session=new_session(db,user,response)
    audit(db,user,"admin_registered",entity_id=user.id,after={"email":user.email,"role":"admin"})
    db.commit()
    return result(db,user,session)


@router.post("/login", response_model=SessionResponse)
def login(data: LoginRequest, request: Request, response: Response, db: Db):
    admin_lock(db)
    email=str(data.email).lower()
    throttle(db,request,email)
    user=db.scalar(select(User).where(User.email==email))
    if user:
        user=locked_user(db,user)
    valid=password_matches(user,data.password) if user else verify_password(data.password,_DUMMY_HASH)
    if not user or not valid or not user.is_active:
        auth_failure(db)
    session=new_session(db,user,response)
    audit(db,user,"password_authenticated", "session",session.id)
    db.commit()
    return result(db,user,session)


@router.post("/refresh", response_model=SessionResponse)
def refresh(request: Request, response: Response, db: Db):
    raw=request.cookies.get(get_settings().cookie_name("refresh"),"")
    user,session=rotate_refresh(db,raw,response)
    return result(db,user,session)


@router.get("/me", response_model=CurrentUserResponse)
def me(request: Request, db: Db, user: Current):
    return current_user_response(db,user,request.state.auth_session)


@router.post("/logout")
def logout(request: Request, response: Response, db: Db):
    admin_lock(db)
    from app.models.authentication import RefreshCredential
    raw=request.cookies.get(get_settings().cookie_name("refresh"),"")
    credential=db.get(RefreshCredential,digest(raw))
    if credential:
        session=db.scalar(select(AuthSession).where(AuthSession.id==credential.session_id).with_for_update())
        session.revoked_at=now()
        audit(db,db.get(User,session.user_id),"logout","session",session.id)
        db.commit()
    clear_cookies(response)
    return {"detail":"Logged out"}


@router.post("/logout-all")
def logout_all(response: Response, db: Db, user: Current):
    revoke_user_sessions(db,user.id)
    audit(db,user,"logout_all",entity_id=user.id)
    db.commit()
    clear_cookies(response)
    return {"detail":"All sessions revoked"}


@router.get("/sessions")
def sessions(request: Request, db: Db, user: Active):
    return [{"id":s.id,"created_at":s.created_at,"last_seen_at":s.last_seen_at,"expires_at":s.expires_at,"current":s.id==request.state.auth_session.id}
        for s in db.scalars(select(AuthSession).where(AuthSession.user_id==user.id,AuthSession.revoked_at.is_(None),AuthSession.expires_at>now()).order_by(AuthSession.created_at.desc()))]


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: str, response: Response, request: Request, db: Db, user: Active):
    session=db.scalar(select(AuthSession).where(AuthSession.id==session_id,AuthSession.user_id==user.id).with_for_update())
    if not session:
        raise HTTPException(404,"Session not found")
    session.revoked_at=now()
    audit(db,user,"session_revoked","session",session.id)
    db.commit()
    if request.state.auth_session.id==session_id:
        clear_cookies(response)
    return {"detail":"Session revoked"}


@router.post("/password", response_model=SessionResponse)
def password_change(data: PasswordChange, request: Request, response: Response, db: Db, user: Current):
    user=lock_current_authority(db,request,user)
    throttle(db,request,str(user.id),"password")
    user=locked_user(db,user)
    if not password_matches(user,data.current_password):
        auth_failure(db,user,"password_change_denied")
    session=request.state.auth_session
    if user.mfa_enabled_at and not session.mfa_verified:
        raise HTTPException(403,"mfa_verification_required")
    if data.new_password.casefold() in {user.email.casefold(),user.full_name.casefold()}:
        raise HTTPException(422,"Passphrase must not equal your email or full name")
    if password_matches(user,data.new_password):
        raise HTTPException(422,"Choose a different passphrase")
    old_policy_version=user.password_policy_version
    user.hashed_password=hash_password(data.new_password)
    user.password_policy_version=1
    revoke_user_sessions(db,user.id)
    replacement=new_session(db,user,response,mfa_verified=session.mfa_verified)
    audit(db,user,"password_changed",entity_id=user.id,before={"password_policy_version":old_policy_version},after={"password_policy_version":1})
    db.commit()
    return result(db,user,replacement)


def validate_assignments(db, role, branch_ids):
    if len(set(branch_ids))!=len(branch_ids) or any(isinstance(b,bool) or b<1 for b in branch_ids):
        raise HTTPException(422,"Assignments must contain unique positive profile IDs")
    active=set(db.scalars(select(Branch.id).where(Branch.id.in_(branch_ids),Branch.is_active.is_(True))))
    if active != set(branch_ids):
        raise HTTPException(422,"Assignments must reference active seller profiles")
    if role==UserRole.STAFF and len(branch_ids)!=1:
        raise HTTPException(422,"Staff must be assigned exactly one seller profile")
    if role==UserRole.MANAGER and not branch_ids:
        raise HTTPException(422,"Manager must be assigned an active seller profile")


def invitation_read(invite):
    return {"id":invite.id,"email":invite.email,"role":invite.role,"branch_ids":invite.branch_ids,
        "expires_at":invite.expires_at,"accepted_at":invite.accepted_at,"revoked_at":invite.revoked_at}


@router.post("/invitations",status_code=201)
def invite_user(data: InvitationCreate, db: Db, user: Admin):
    admin_lock(db)
    validate_assignments(db,data.role,data.branch_ids)
    email=str(data.email).lower()
    if db.scalar(select(User.id).where(User.email==email)):
        raise HTTPException(409,"An account with this email already exists")
    raw=secrets.token_urlsafe(48)
    invite=AccountInvitation(email=email,role=data.role.value,branch_ids=data.branch_ids,token_hash=digest(raw),created_by_id=user.id,created_at=now(),expires_at=now()+timedelta(hours=48))
    db.add(invite)
    db.flush()
    audit(db,user,"invitation_created","invitation",invite.id,after={"email":email,"role":data.role.value,"branch_ids":data.branch_ids})
    db.commit()
    return {**invitation_read(invite),"token":raw}


@router.get("/invitations")
def invitations(db: Db, user: Admin):
    return [invitation_read(i) for i in db.scalars(select(AccountInvitation).order_by(AccountInvitation.id.desc()).limit(100))]


@router.delete("/invitations/{invitation_id}")
def revoke_invitation(invitation_id:int, db: Db, user: Admin):
    invite=db.scalar(select(AccountInvitation).where(AccountInvitation.id==invitation_id).with_for_update())
    if not invite:
        raise HTTPException(404,"Invitation not found")
    invite.revoked_at=now()
    audit(db,user,"invitation_revoked","invitation",invite.id)
    db.commit()
    return {"detail":"Invitation revoked"}


@router.post("/invitations/accept",response_model=SessionResponse,status_code=201)
def accept_invitation(data: InvitationAccept, request: Request, response: Response, db: Db):
    admin_lock(db)
    throttle(db,request,digest(data.token),"invite")
    admin_lock(db)
    invite=db.scalar(select(AccountInvitation).where(AccountInvitation.token_hash==digest(data.token)).with_for_update())
    if not invite or invite.accepted_at or invite.revoked_at or aware(invite.expires_at)<=now():
        auth_failure(db,action="invitation_accept_denied")
    if db.scalar(select(User.id).where(User.email==invite.email)):
        auth_failure(db,action="invitation_accept_denied")
    validate_assignments(db,UserRole(invite.role),invite.branch_ids)
    user=User(email=invite.email,full_name=data.full_name,role=UserRole(invite.role),hashed_password=hash_password(data.password),password_policy_version=1,is_active=True)
    db.add(user)
    db.flush()
    for branch_id in invite.branch_ids:
        db.add(UserBranchAssignment(user_id=user.id,branch_id=branch_id))
    invite.accepted_at=now()
    session=new_session(db,user,response)
    audit(db,user,"invitation_accepted","invitation",invite.id,after={"role":invite.role})
    db.commit()
    return result(db,user,session)


def mfa_reauth(data, db, user):
    user=locked_user(db,user)
    if not data.current_password or not password_matches(user,data.current_password) or not verify_totp(db,user,data.code):
        auth_failure(db,user,"mfa_change_denied")


@router.post("/mfa/enroll")
def enroll_mfa(data: MFAReauthentication, request: Request, db: Db, user: Current):
    user=lock_current_authority(db,request,user)
    throttle(db,request,str(user.id),"mfa")
    user=locked_user(db,user)
    if user.password_policy_version < 1:
        raise HTTPException(403,"password_change_required")
    if user.mfa_enabled_at:
        mfa_reauth(data,db,user)
    secret=pyotp.random_base32()
    user.mfa_pending_secret=cipher().encrypt(secret.encode()).decode()
    user.mfa_pending_expires_at=now()+timedelta(minutes=10)
    audit(db,user,"mfa_enrollment_started",entity_id=user.id)
    db.commit()
    return {"secret":secret,"provisioning_uri":pyotp.TOTP(secret).provisioning_uri(name=user.email,issuer_name="Pristine Bio Billing")}


@router.post("/mfa/confirm")
def confirm_mfa(data: MFACode, request: Request, response: Response, db: Db, user: Current):
    user=lock_current_authority(db,request,user)
    throttle(db,request,str(user.id),"mfa")
    user=locked_user(db,user)
    if user.password_policy_version < 1:
        raise HTTPException(403,"password_change_required")
    if not user.mfa_pending_secret or not user.mfa_pending_expires_at or aware(user.mfa_pending_expires_at)<=now():
        raise HTTPException(422,"Authenticator enrollment expired. Start enrollment again.")
    secret=cipher().decrypt(user.mfa_pending_secret.encode()).decode()
    if len(data.code)!=6 or not data.code.isascii() or not data.code.isdigit() or not pyotp.TOTP(secret).verify(data.code,valid_window=1):
        auth_failure(db,user,"mfa_confirmation_denied")
    previously_enabled=user.mfa_enabled_at is not None
    user.mfa_secret=user.mfa_pending_secret
    user.mfa_enabled_at=now()
    user.mfa_reenrollment_required=False
    user.mfa_last_step=None
    db.flush()
    verify_totp(db,user,data.code)
    user.mfa_pending_secret=user.mfa_pending_expires_at=None
    codes=replace_recovery_codes(db,user)
    revoke_user_sessions(db,user.id)
    session=new_session(db,user,response,mfa_verified=True)
    audit(db,user,"mfa_enrolled",entity_id=user.id,before={"mfa_enabled":previously_enabled},after={"mfa_enabled":True})
    db.commit()
    return {"user":current_user_response(db,user,session),"recovery_codes":codes}


@router.post("/mfa/verify", response_model=SessionResponse)
def verify_mfa(data: MFACode, request: Request, response: Response, db: Db, user: Current):
    user=lock_current_authority(db,request,user)
    throttle(db,request,str(user.id),"mfa")
    if not verify_totp(db,user,data.code):
        auth_failure(db,user,"mfa_verification_denied")
    request.state.auth_session.revoked_at=now()
    session=new_session(db,user,response,mfa_verified=True)
    audit(db,user,"mfa_authenticated","session",session.id)
    db.commit()
    return result(db,user,session)


@router.post("/mfa/recover",response_model=SessionResponse)
def recover_mfa(data: MFACode, request: Request, response: Response, db: Db, user: Current):
    user=lock_current_authority(db,request,user)
    throttle(db,request,str(user.id),"mfa")
    user=locked_user(db,user)
    recovery=db.scalar(select(MFARecoveryCode).where(MFARecoveryCode.user_id==user.id,MFARecoveryCode.code_hash==digest(data.code),MFARecoveryCode.used_at.is_(None)).with_for_update())
    if not recovery:
        auth_failure(db,user,"mfa_recovery_denied")
    recovery.used_at=now()
    reset_mfa(db,user)
    session=new_session(db,user,response)
    audit(db,user,"mfa_recovered_reenrollment_required",entity_id=user.id,before={"mfa_enabled":True},after={"mfa_enabled":False})
    db.commit()
    return result(db,user,session)


@router.post("/mfa/recovery-codes")
def regenerate_recovery(data: MFAReauthentication, request: Request, db: Db, user: Active):
    user=lock_current_authority(db,request,user)
    throttle(db,request,str(user.id),"mfa")
    mfa_reauth(data,db,user)
    codes=replace_recovery_codes(db,user)
    audit(db,user,"mfa_recovery_codes_replaced",entity_id=user.id)
    db.commit()
    return {"recovery_codes":codes}


@router.get("/audit")
def security_audit(db: Db, user: Admin):
    return [{"id":e.id,"actor_id":e.actor_id,"action":e.action,"entity_type":e.entity_type,"entity_id":e.entity_id,"created_at":e.created_at,"before":e.before,"after":e.after}
        for e in db.scalars(select(SecurityAudit).order_by(SecurityAudit.id.desc()).limit(100))]
