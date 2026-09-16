from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.user import CurrentUserResponse, validate_password_strength


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=6)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=6, max_length=6)
    master_password: str = Field(min_length=1, max_length=512)

    @field_validator("password")
    @classmethod
    def password_is_strong(cls, password: str) -> str:
        return validate_password_strength(password)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: Literal["bearer"] = "bearer"
    user: CurrentUserResponse | None = None
