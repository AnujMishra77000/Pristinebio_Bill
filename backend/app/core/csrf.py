"""Signed, session-bound double-submit plus exact origin protection."""
import hashlib
import hmac
import secrets
import time
import jwt
from starlette.responses import JSONResponse
from app.core.config import get_settings


def binding(request):
    settings = get_settings()
    token = request.cookies.get(settings.cookie_name("access"))
    if token:
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm], options={"verify_exp":False})
            return str(payload.get("sid", "anonymous"))
        except jwt.PyJWTError:
            pass
    return "anonymous"


def issue_csrf(request):
    existing=request.cookies.get(get_settings().cookie_name("csrf"),"")
    if token_valid(existing,request):
        return existing
    value = f"{binding(request)}.{int(time.time())}.{secrets.token_urlsafe(24)}"
    signature = hmac.new(get_settings().jwt_secret_key.encode(), ("csrf:"+value).encode(), hashlib.sha256).hexdigest()
    return value+"."+signature


def valid_csrf(request):
    value = request.headers.get("X-CSRF-Token", "")
    cookie = request.cookies.get(get_settings().cookie_name("csrf"), "")
    if not value or not secrets.compare_digest(value, cookie):
        return False
    return token_valid(value,request)


def token_valid(value,request):
    try:
        bound, timestamp, nonce, signature = value.split(".")
        unsigned = f"{bound}.{timestamp}.{nonce}"
        expected = hmac.new(get_settings().jwt_secret_key.encode(), ("csrf:"+unsigned).encode(), hashlib.sha256).hexdigest()
        return secrets.compare_digest(signature, expected) and bound == binding(request) and 0 <= time.time()-int(timestamp) < 3600
    except (ValueError, TypeError):
        return False


async def security_middleware(request, call_next):
    if request.url.path.startswith("/api/v1") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("Origin") not in get_settings().allowed_origins:
            return JSONResponse({"detail":"Request origin is not permitted"}, status_code=403)
        if not valid_csrf(request):
            return JSONResponse({"detail":"CSRF validation failed; retry after renewing the security token"}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith("/api/v1/auth"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response
