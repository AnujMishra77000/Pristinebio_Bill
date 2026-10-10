from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.financial_validation import optional_text, required_text, state_code


def serialize_decimal(value: Decimal) -> str:
    return str(value)


class BillDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(gt=0, strict=True)
    confirmation_number: str = Field(min_length=1, max_length=100)
    document_type: Literal["sales", "domestic_oils", "reagent"]

    @field_validator("confirmation_number", mode="before")
    @classmethod
    def validate_confirmation(cls, value: str) -> str:
        return required_text(value, "Confirmation bill number")


class AddressPayload(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    address_line1: str = Field(min_length=1, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    state_code: str = Field(min_length=2, max_length=2)
    postal_code: str = Field(min_length=1, max_length=20)

    @field_validator("name", "address_line2", mode="before")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        return optional_text(value, "Address field")

    @field_validator("address_line1", "city", "state", "postal_code", mode="before")
    @classmethod
    def validate_required_fields(cls, value: str) -> str:
        return required_text(value, "Address field")

    @field_validator("state_code", mode="before")
    @classmethod
    def validate_state_code(cls, value: str) -> str:
        return state_code(value)


class AddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    state_code: str | None
    postal_code: str | None
