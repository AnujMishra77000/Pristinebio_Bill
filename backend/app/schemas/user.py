from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole


def validate_password_strength(password: str) -> str:
    if len(password) != 6:
        raise ValueError("Password must be exactly 6 characters long")
    if not any(character.islower() for character in password):
        raise ValueError("Password must include a lowercase letter")
    if not any(character.isupper() for character in password):
        raise ValueError("Password must include an uppercase letter")
    if not any(character.isdigit() for character in password):
        raise ValueError("Password must include a number")
    return password


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    branch_ids: list[int]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=6, max_length=6)
    role: UserRole
    branch_ids: list[int] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("password")
    @classmethod
    def password_is_strong(cls, password: str) -> str:
        return validate_password_strength(password)


class AdminBootstrapCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=6, max_length=6)

    @field_validator("password")
    @classmethod
    def password_is_strong(cls, password: str) -> str:
        return validate_password_strength(password)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    password: str | None = Field(default=None, min_length=6, max_length=6)
    role: UserRole | None = None
    branch_ids: list[int] | None = None
    is_active: bool | None = None

    @field_validator("password")
    @classmethod
    def password_is_strong(cls, password: str | None) -> str | None:
        if password is None:
            return None
        return validate_password_strength(password)


class UserRead(CurrentUserResponse):
    is_active: bool
