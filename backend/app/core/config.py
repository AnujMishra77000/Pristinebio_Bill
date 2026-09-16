from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://billing:billing@localhost:5432/billing"
    frontend_origin: str = "http://localhost:3000"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: str = "local-development-secret-change-before-use"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    admin_bootstrap_token: str | None = None
    admin_registration_master_password: str | None = None
    pdf_storage_dir: str = "./storage/invoices"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
