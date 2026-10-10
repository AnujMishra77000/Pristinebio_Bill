from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from app.core.security import validate_passphrase
from app.models.enums import UserRole
from app.schemas.user import CurrentUserResponse, PassphraseIdentity


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class SessionResponse(BaseModel):
    user: CurrentUserResponse


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(max_length=256)
    _password = field_validator("new_password")(validate_passphrase)


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    role: UserRole
    branch_ids: list[int] = Field(default_factory=list)


class InvitationAccept(PassphraseIdentity):
    email: EmailStr | None = None
    token: str = Field(min_length=32, max_length=256)


class MFACode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=6, max_length=64)


class MFAReauthentication(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str | None = Field(default=None, max_length=256)
    code: str | None = Field(default=None, min_length=6, max_length=64)


class MFAReset(MFAReauthentication):
    reason: str = Field(min_length=1, max_length=1000)
    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Reset reason is required")
        return value.strip()
