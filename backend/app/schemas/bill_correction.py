from pydantic import ConfigDict, Field, field_validator

from app.schemas.invoice import InvoiceUpdate
from app.schemas.purchase_order import PurchaseOrderUpdate, PurchaseOrderReasonAction
from app.services.financial_validation import required_text


class CorrectionAction(PurchaseOrderReasonAction):
    expected_version: int = Field(gt=0, strict=True)
    reason: str = Field(default="", max_length=2000)


class CorrectionRestart(PurchaseOrderReasonAction):
    expected_version: int = Field(gt=0, strict=True)
    correction_version: int = Field(gt=0, strict=True)


class InvoiceCorrectionUpdate(InvoiceUpdate):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(gt=0, strict=True)
    correction_reason: str = Field(min_length=1, max_length=2000)

    @field_validator("correction_reason", mode="before")
    @classmethod
    def normalize_reason(cls, value):
        return required_text(value, "Correction reason")


class PurchaseOrderCorrectionUpdate(PurchaseOrderUpdate):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(gt=0, strict=True)
    correction_reason: str = Field(min_length=1, max_length=2000)

    @field_validator("correction_reason", mode="before")
    @classmethod
    def normalize_reason(cls, value):
        return required_text(value, "Correction reason")
