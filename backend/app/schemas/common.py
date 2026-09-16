from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


def serialize_decimal(value: Decimal) -> str:
    return str(value)


class AddressPayload(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    address_line1: str = Field(min_length=1, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    state_code: str = Field(min_length=2, max_length=2)
    postal_code: str = Field(min_length=1, max_length=20)


class AddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str | None
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    state_code: str | None
    postal_code: str | None
