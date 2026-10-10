"""Security primitives; never place credential material in audit records."""
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pyotp
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.authentication import AuthSession, AuthThrottle, MFARecoveryCode, RefreshCredential, SecurityAudit
from app.models.user import User


def now():
    return datetime.now(UTC)


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def cipher():
    key = get_settings().mfa_encryption_key
    if not key:
        raise HTTPException(503, "MFA_ENCRYPTION_KEY must be configured before account setup or MFA")
    return Fernet(key.encode())


def audit(db, actor, action, entity_type="user", entity_id=None, before=None, after=None):
    db.add(SecurityAudit(actor_id=actor.id if actor else None, action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None, created_at=now(), before=before, after=after))


def snapshot(record):
    from sqlalchemy import inspect
    from fastapi.encoders import jsonable_encoder
    value = jsonable_encoder({col.key: getattr(record, col.key) for col in inspect(record).mapper.column_attrs if col.key not in {"hashed_password", "mfa_secret", "mfa_pending_secret", "mfa_last_step", "logo_data_uri"}})
    if hasattr(record,"logo_data_uri"):
        value["logo_sha256"] = digest(record.logo_data_uri) if record.logo_data_uri else None
    return value


def admin_lock(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 5_273_476_181})


def throttle(db, request, subject: str, category="login"):
    # Proxy headers are not trusted; production must configure its trusted proxy.
    ip = request.client.host if request.client else "unknown"
    pairs = sorted([(digest(f"{category}:subject:{subject}"), 8), (digest(f"{category}:ip:{ip}"), 40)])
    for key, limit in pairs:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(key[:15], 16)})
        insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
        db.execute(insert(AuthThrottle).values(bucket=key, window_started_at=now(), attempts=0).on_conflict_do_nothing(index_elements=[AuthThrottle.bucket]))
        bucket = db.scalar(select(AuthThrottle).where(AuthThrottle.bucket == key).with_for_update().execution_options(populate_existing=True))
        if aware(bucket.window_started_at) + timedelta(minutes=15) <= now():
            bucket.window_started_at, bucket.attempts = now(), 0
        bucket.attempts += 1
        if bucket.attempts > limit:
            audit(db, None, "authentication_throttled", "throttle", key)
            db.commit()
            raise HTTPException(429, "Too many authentication attempts. Try again later.", headers={"Retry-After":"900"})
    db.flush()


def requires_mfa(user):
    """MFA is retained only for legacy data and is not part of active login."""
    return False


def session_valid(session, user):
    if not session or not user or not user.is_active or session.revoked_at:
        return False
    idle = timedelta(minutes=get_settings().session_idle_minutes)
    return aware(session.expires_at) > now() and aware(session.last_seen_at) + idle > now()


def set_cookie(response, kind, value, max_age):
    settings = get_settings()
    response.set_cookie(settings.cookie_name(kind), value, httponly=True, secure=settings.cookie_secure, samesite="lax", path="/", max_age=max_age)


def clear_cookies(response):
    settings = get_settings()
    for kind in ("access", "refresh", "csrf"):
        response.delete_cookie(settings.cookie_name(kind), path="/", secure=settings.cookie_secure, httponly=True, samesite="lax")


def session_cookies(response, session, user, refresh_token):
    settings = get_settings()
    remaining = max(0, int((aware(session.expires_at) - now()).total_seconds()))
    set_cookie(response, "access", create_access_token(str(user.id), user.role, session.id), min(settings.access_token_expire_minutes * 60, remaining))
    set_cookie(response, "refresh", refresh_token, remaining)


def new_session(db, user, response, mfa_verified=False):
    raw = secrets.token_urlsafe(48)
    restricted = user.password_policy_version < 1 or (requires_mfa(user) and not mfa_verified)
    ttl = timedelta(minutes=10) if restricted else timedelta(days=get_settings().refresh_token_expire_days)
    session = AuthSession(id=str(uuid4()), user_id=user.id, created_at=now(), last_seen_at=now(), expires_at=now()+ttl, mfa_verified=mfa_verified, current_refresh_hash=digest(raw))
    db.add(session)
    db.flush()
    db.add(RefreshCredential(token_hash=digest(raw), session_id=session.id))
    session_cookies(response, session, user, raw)
    return session


def revoke_user_sessions(db, user_id, except_id=None):
    statement = update(AuthSession).where(AuthSession.user_id==user_id, AuthSession.revoked_at.is_(None))
    if except_id:
        statement = statement.where(AuthSession.id != except_id)
    db.execute(statement.values(revoked_at=now()))


def rotate_refresh(db, raw, response):
    admin_lock(db)
    credential = db.get(RefreshCredential, digest(raw))
    if not credential:
        raise HTTPException(401, "Session expired or revoked. Sign in again.")
    session = db.scalar(select(AuthSession).where(AuthSession.id == credential.session_id).with_for_update().execution_options(populate_existing=True))
    user = db.get(User, session.user_id)
    if not session_valid(session, user):
        raise HTTPException(401, "Session expired or revoked. Sign in again.")
    db.refresh(credential)
    if credential.consumed_at:
        grace = get_settings().refresh_concurrency_grace_seconds
        if credential.successor_hash == session.current_refresh_hash and aware(credential.consumed_at)+timedelta(seconds=grace) > now():
            successor = cipher().decrypt(credential.successor_encrypted.encode()).decode()
        else:
            session.revoked_at = now()
            audit(db, user, "refresh_replay_revoked", "session", session.id)
            db.commit()
            raise HTTPException(401, "Session expired or revoked. Sign in again.")
    else:
        # Older hashes stay for replay detection, but recoverable successor
        # material is no longer needed once the next generation is rotated.
        db.execute(update(RefreshCredential).where(RefreshCredential.session_id==session.id).values(successor_encrypted=None))
        successor = secrets.token_urlsafe(48)
        credential.consumed_at = now()
        credential.successor_hash = digest(successor)
        credential.successor_encrypted = cipher().encrypt(successor.encode()).decode()
        session.current_refresh_hash = digest(successor)
        db.add(RefreshCredential(token_hash=digest(successor), session_id=session.id))
    session.last_seen_at = now()
    session_cookies(response, session, user, successor)
    db.commit()
    return user, session


def locked_user(db, user):
    return db.scalar(select(User).where(User.id==user.id).with_for_update().execution_options(populate_existing=True))


def lock_current_authority(db, request, user, admin=False):
    admin_lock(db)
    user=locked_user(db,user)
    source=request.state.auth_session
    session=db.scalar(select(AuthSession).where(AuthSession.id==source.id).with_for_update().execution_options(populate_existing=True))
    if not session_valid(session,user) or session.user_id!=user.id:
        raise HTTPException(401,"Session expired or revoked. Sign in again.")
    if admin and (user.role!=UserRole.ADMIN or user.password_policy_version<1 or not user.mfa_enabled_at or not session.mfa_verified):
        raise HTTPException(403,"Insufficient permissions")
    request.state.auth_session=session
    return user


def verify_totp(db, user, code):
    user = locked_user(db, user)
    if not user.mfa_secret or not code or not code.isascii() or not code.isdigit() or len(code)!=6:
        return False
    totp = pyotp.TOTP(cipher().decrypt(user.mfa_secret.encode()).decode())
    step = int(now().timestamp()) // 30
    for offset in (0, -1, 1):
        candidate = step + offset
        if (user.mfa_last_step is None or candidate > user.mfa_last_step) and secrets.compare_digest(totp.at(candidate*30), code):
            user.mfa_last_step = candidate
            db.flush()
            return True
    return False


def replace_recovery_codes(db, user):
    db.execute(delete(MFARecoveryCode).where(MFARecoveryCode.user_id==user.id))
    codes = [secrets.token_hex(10) for _ in range(10)]
    for code in codes:
        db.add(MFARecoveryCode(user_id=user.id, code_hash=digest(code)))
    return codes


def reset_mfa(db, user):
    user.mfa_secret = user.mfa_pending_secret = user.mfa_pending_expires_at = user.mfa_enabled_at = user.mfa_last_step = None
    user.mfa_reenrollment_required = True
    db.execute(delete(MFARecoveryCode).where(MFARecoveryCode.user_id==user.id))
    revoke_user_sessions(db, user.id)
