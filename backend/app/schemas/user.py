from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from app.core.security import validate_passphrase
from app.models.enums import UserRole

validate_password_strength = validate_passphrase


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    branch_ids: list[int]
    is_active: bool = True
    password_change_required: bool = False
    mfa_enabled: bool = False
    mfa_required: bool = False
    mfa_verified: bool = False


class PassphraseIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(max_length=256)
    _password = field_validator("password")(validate_passphrase)

    @field_validator("full_name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Full name is required")
        return value.strip()


class AdminRegistrationCreate(PassphraseIdentity):
    email: EmailStr


class UserCreate(PassphraseIdentity):
    email: EmailStr
    role: UserRole
    branch_ids: list[int] = Field(default_factory=list)
    is_active: bool = True


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: UserRole | None = None
    branch_ids: list[int] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def explicit_nulls_not_allowed(self):
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} may not be null; omit it to leave unchanged")
        if self.full_name is not None:
            if not self.full_name.strip():
                raise ValueError("Full name is required")
            self.full_name = self.full_name.strip()
        return self


class UserRead(CurrentUserResponse):
    pass
