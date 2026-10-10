from datetime import UTC, datetime, timedelta
from typing import Any
import unicodedata
from functools import lru_cache
from pathlib import Path

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.models.enums import UserRole


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return password_hash.verify(plain_password, hashed_password)
    except Exception:
        return False


@lru_cache
def common_passwords() -> frozenset[str]:
    return frozenset(Path(__file__).with_name("common_passwords.txt").read_text(encoding="utf-8").splitlines()) | frozenset({"passwordpassword", "123456789012345", "1234567890123456", "pristine biopharma", "pristinebiopharma"})


def validate_passphrase(password: str) -> str:
    password = unicodedata.normalize("NFC", password)
    if not 6 <= len(password) <= 10:
        raise ValueError("Passphrase must contain 6 to 10 characters")
    if not password.strip() or password.casefold() in common_passwords() or len(set(password)) == 1:
        raise ValueError("Choose a passphrase that is not common, compromised or repetitive")
    return password


def _create_token(
    subject: str,
    role: UserRole,
    token_type: str,
    expires_delta: timedelta,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role.value,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, role: UserRole, session_id: str | None = None) -> str:
    settings = get_settings()
    token = _create_token(
        subject=subject,
        role=role,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    if session_id is None:
        return token
    payload = decode_token(token, "access")
    payload["sid"] = session_id
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, role: UserRole) -> str:
    settings = get_settings()
    return _create_token(
        subject=subject,
        role=role,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise ValueError("Invalid token") from exc
    if payload.get("typ") != expected_type:
        raise ValueError("Invalid token type")
    return payload
