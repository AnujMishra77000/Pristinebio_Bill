from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.financial_validation import optional_text, required_text


class IntegrationJobCreate(BaseModel):
    invoice_id: int
    branch_id: int | None = None
    provider_key: str = Field(min_length=1, max_length=80)
    operation: str = Field(default="invoice_submission", min_length=1, max_length=40)
    claimed_external_reference: str | None = Field(default=None, max_length=255)

    @field_validator("provider_key", "operation", mode="before")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        value = required_text(value, "Integration identifier").lower()
        if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in value):
            raise ValueError("Integration identifiers may contain only letters, numbers, dot, underscore and hyphen")
        return value

    @field_validator("claimed_external_reference", mode="before")
    @classmethod
    def normalize_claimed_reference(cls, value: str | None) -> str | None:
        return optional_text(value, "Claimed external reference")


class IntegrationJobRead(BaseModel):
    id: int
    branch_id: int
    invoice_id: int
    provider_key: str
    operation: str
    idempotency_key: str
    payload_hash: str
    status: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    external_reference: str | None
    external_status: str | None
    external_submitted_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime


class ProviderResponse(BaseModel):
    """Validated contract a future provider adapter must satisfy."""

    status: str
    external_reference: str | None = Field(default=None, max_length=255)
    submitted_at: datetime | None = None
    payload: dict = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = required_text(value, "Provider response status").lower()
        if value not in {"accepted", "rejected", "uncertain"}:
            raise ValueError("Provider response status is not supported")
        return value

    @model_validator(mode="after")
    def require_authoritative_fields(self):
        if self.status == "accepted" and (not self.external_reference or self.submitted_at is None):
            raise ValueError("Accepted provider responses require an external reference and submission timestamp")
        return self


class IntegrationPage(BaseModel):
    items: list[IntegrationJobRead]
    total: int
    page: int
    page_size: int


class ReconciliationRead(BaseModel):
    id: int
    job_id: int
    difference_type: str
    status: str
    local_status: str
    external_status: str | None
    external_reference: str | None
    details: dict
    detected_at: datetime
    resolved_at: datetime | None
    resolution_note: str | None


class ReconciliationPage(BaseModel):
    items: list[ReconciliationRead]
    total: int
    page: int
    page_size: int


class ProviderRead(BaseModel):
    provider_key: str
    available: bool
    environment: str
    reason: str


class NumberingReview(BaseModel):
    current_series: str
    compatibility: str
    proposed_series: str
    migration_policy: str


class InvoiceIntegrationStatus(BaseModel):
    invoice_id: int
    local_status: str
    external_jobs: list[IntegrationJobRead]


class CancelIntegrationJob(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return required_text(value, "Cancellation reason")
