from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.schemas.common import serialize_decimal
from app.services.financial_validation import normalize_money, optional_text, required_text


def currency(value: str) -> str:
    value = value.strip().upper()
    if len(value) != 3 or not value.isalpha():
        raise ValueError("Currency must be a three-letter ISO code")
    return value


class ReceiptCreate(BaseModel):
    customer_id: int
    receipt_date: date
    currency: str = "INR"
    amount: Decimal = Field(gt=Decimal("0"))
    reference: str | None = Field(default=None, max_length=255)
    notes: str | None = None

    @field_validator("currency", mode="before")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return currency(value)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        return normalize_money(value, "Receipt amount")

    @field_validator("reference", "notes", mode="before")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return optional_text(value, "Receipt detail")


class AllocationCreate(BaseModel):
    receipt_id: int
    invoice_id: int
    amount: Decimal = Field(gt=Decimal("0"))

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        return normalize_money(value, "Allocation amount")


class ReversalCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return required_text(value, "Reversal reason")


class CreditLimitUpsert(BaseModel):
    currency: str = "INR"
    limit_amount: Decimal = Field(ge=Decimal("0"))
    is_active: bool = True

    @field_validator("currency", mode="before")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return currency(value)

    @field_validator("limit_amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        return normalize_money(value, "Credit limit")


class CreditOverrideCreate(BaseModel):
    currency: str = "INR"
    amount: Decimal = Field(gt=Decimal("0"))
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("currency", mode="before")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return currency(value)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        return normalize_money(value, "Override amount")

    @field_validator("reason", mode="before")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return required_text(value, "Credit override reason")


class ReceiptRead(BaseModel):
    id: int
    branch_id: int
    customer_id: int
    receipt_number: str
    receipt_date: date
    currency: str
    amount: Decimal
    allocated_amount: Decimal
    unallocated_amount: Decimal
    reference: str | None
    notes: str | None
    status: str
    version: int
    created_at: datetime

    @field_serializer("amount", "allocated_amount", "unallocated_amount")
    def serialize_money(self, value: Decimal) -> str:
        return serialize_decimal(value)


class AllocationRead(BaseModel):
    id: int
    receipt_id: int
    invoice_id: int
    amount: Decimal
    currency: str
    created_at: datetime
    reversed_at: datetime | None

    @field_serializer("amount")
    def serialize_money(self, value: Decimal) -> str:
        return serialize_decimal(value)


class StatementItem(BaseModel):
    invoice_id: int
    invoice_number: str | None
    invoice_date: date
    due_date: date | None
    currency: str
    invoice_total: Decimal
    allocated_amount: Decimal
    outstanding_amount: Decimal
    overdue_days: int

    @field_serializer("invoice_total", "allocated_amount", "outstanding_amount")
    def serialize_money(self, value: Decimal) -> str:
        return serialize_decimal(value)


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
