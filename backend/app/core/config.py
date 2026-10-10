from functools import lru_cache
import base64
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://billing:billing@localhost:5432/billing"
    frontend_origin: str = "http://localhost:3000"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str = "local-development-secret-change-before-use"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=15, ge=1, le=30)
    refresh_token_expire_days: int = Field(default=14, ge=1, le=30)
    session_idle_minutes: int = Field(default=480, ge=5, le=1440)
    refresh_concurrency_grace_seconds: int = Field(default=10, ge=0, le=15)
    cookie_secure: bool = False
    mfa_encryption_key: str | None = None
    pdf_storage_dir: str = "./storage/invoices"
    web_concurrency: int = Field(default=2, ge=1, le=16)
    error_tracking_dsn: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    @model_validator(mode="after")
    def validate_security(self):
        origin = urlsplit(self.frontend_origin)
        if origin.scheme not in {"http", "https"} or not origin.netloc or origin.path not in {"", "/"} or origin.query or origin.fragment or origin.username:
            raise ValueError("FRONTEND_ORIGIN must be an exact HTTP(S) origin")
        if self.jwt_algorithm != "HS256":
            raise ValueError("JWT_ALGORITHM must be HS256")
        if self.app_environment.lower() not in {"development", "dev", "test", "production"}:
            raise ValueError("APP_ENVIRONMENT must be development, test or production")
        if self.mfa_encryption_key:
            try:
                if len(base64.urlsafe_b64decode(self.mfa_encryption_key)) != 32:
                    raise ValueError
            except (ValueError, TypeError):
                raise ValueError("MFA_ENCRYPTION_KEY must be a Fernet key") from None
        if self.app_environment.lower() == "production":
            def strong(value: str | None) -> bool:
                return bool(value and len(value) >= 32 and len(set(value)) >= 16 and not any(word in value.lower() for word in ("replace", "development", "change-before", "example", "default")))
            if not strong(self.jwt_secret_key):
                raise ValueError("Production requires a strong JWT_SECRET_KEY")
            if self.jwt_secret_key == self.mfa_encryption_key:
                raise ValueError("Signing and encryption keys must be independent")
            if not self.cookie_secure or origin.scheme != "https":
                raise ValueError("Production requires COOKIE_SECURE=true and an HTTPS FRONTEND_ORIGIN")
            from sqlalchemy.engine import make_url
            password = make_url(self.database_url).password
            if not password or password in {"billing", "postgres", "password", "changeme"}:
                raise ValueError("Production DATABASE_URL requires non-default database credentials")
        return self

    @property
    def allowed_origins(self) -> list[str]:
        origins = [self.frontend_origin.rstrip("/")]
        if self.app_environment.lower() in {"development", "dev", "test"}:
            origins = list(dict.fromkeys(origins + ["http://localhost:3000", "http://127.0.0.1:3000"]))
        return origins

    def cookie_name(self, kind: str) -> str:
        return ("__Host-" if self.cookie_secure else "") + "billing_" + kind


@lru_cache
def get_settings() -> Settings:
    return Settings()
