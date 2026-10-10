from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_serializer, field_validator, model_validator

from app.schemas.common import serialize_decimal
from app.schemas.master_records import PurchaserCreate, SupplierCreate
from app.schemas.invoice import InvoiceLineInput
from app.services.financial_validation import normalize_money, optional_text, required_text, state_code


def normalize_purchase_order_number(value: str | None) -> str | None:
    if value is None:
        return None
    value = required_text(value, "PO No.")
    if not value.isprintable():
        raise ValueError("PO No. must be a single line without control characters")
    return value.upper()


class PurchaseOrderCreate(BaseModel):
    document_type: Literal["domestic_oils", "reagent"] = "domestic_oils"
    purchase_order_number: str | None = Field(default=None, max_length=100)
    branch_id: int | None = None
    supplier_id: int | None = None
    supplier: SupplierCreate | None = None
    purchaser_id: int | None = None
    purchaser: PurchaserCreate | None = None
    save_purchaser_for_future: bool = False
    order_date: date
    expected_delivery_date: date | None = None
    payment_terms: str | None = Field(default=None, max_length=255)
    place_of_supply_state_code: str | None = None
    delivery_note_date: date | None = None
    po_reference_number: str | None = Field(default=None, max_length=100)
    po_reference_date: date | None = None
    transport_mode: str | None = Field(default=None, max_length=100)
    vehicle_number: str | None = Field(default=None, max_length=30)
    vehicle_type: str | None = Field(default=None, max_length=100)
    lr_number: str | None = Field(default=None, max_length=100)
    lr_date: date | None = None
    consignee: PurchaserCreate | None = None
    freight_charges: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    packing_charges: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    other_charges: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    lines: list[InvoiceLineInput] = Field(min_length=1)

    @field_validator("purchase_order_number", mode="before")
    @classmethod
    def validate_purchase_order_number(cls, value: str | None) -> str | None:
        return normalize_purchase_order_number(value)

    @field_validator("place_of_supply_state_code")
    @classmethod
    def validate_place_of_supply(cls, value: str | None) -> str | None:
        return state_code(value) if value is not None else None

    @field_validator("po_reference_number", "transport_mode", "vehicle_number", "vehicle_type", "lr_number", mode="before")
    @classmethod
    def normalize_reference(cls, value: str | None, info: ValidationInfo) -> str | None:
        return optional_text(value, info.field_name.replace("_", " "))

    @model_validator(mode="after")
    def validate_reagent_details(self):
        if self.document_type == "reagent":
            if self.place_of_supply_state_code is None:
                raise ValueError("Place of supply is required for a reagent purchase order")
            if self.purchaser is not None and not self.purchaser.is_active:
                raise ValueError("Purchaser cannot be inactive")
            if self.consignee is not None and not self.consignee.is_active:
                raise ValueError("Consignee cannot be inactive")
        return self

    @field_validator("payment_terms", mode="before")
    @classmethod
    def normalize_payment_terms(cls, value: str | None) -> str | None:
        return optional_text(value, "Payment terms")

    @field_validator("freight_charges", "packing_charges", "other_charges", "discount_amount")
    @classmethod
    def validate_document_money(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        return normalize_money(value, info.field_name.replace("_", " ").title())


class PurchaseOrderLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    sort_order: int
    product_name: str
    manufacturer_id: int | None
    manufacturer_name: str | None
    manufacturer_code: str | None
    manufacturer_product_code: str | None
    part_no: str | None
    pack_size: str | None = None
    discount_percent: Decimal
    description: str
    hsn_sac: str
    quantity: Decimal
    unit: str
    rate: Decimal
    other_charge: Decimal
    discount_amount: Decimal
    taxable_value: Decimal
    gst_rate: Decimal
    cess_rate: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    line_total: Decimal

    @field_serializer(
        "quantity",
        "rate",
        "other_charge",
        "discount_amount",
        "discount_percent",
        "taxable_value",
        "gst_rate",
        "cess_rate",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "line_total",
    )
    def serialize_decimal_fields(self, value: Decimal) -> str:
        return serialize_decimal(value)


class PurchaseOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: int
    supplier_id: int
    purchaser_id: int | None
    created_by_id: int
    purchase_order_number: str
    order_date: date
    document_type: Literal["domestic_oils", "reagent"]
    place_of_supply_state_code: str | None
    delivery_note_date: date | None
    po_reference_number: str | None
    po_reference_date: date | None
    transport_mode: str | None
    vehicle_number: str | None
    vehicle_type: str | None
    lr_number: str | None
    lr_date: date | None
    consignee: dict | None = Field(validation_alias="consignee_details")
    expected_delivery_date: date | None
    payment_terms: str | None
    status: str
    version: int
    submitted_revision: int | None
    approved_revision: int | None
    submitted_by_id: int | None
    approved_by_id: int | None
    submitted_at: datetime | None
    approved_at: datetime | None
    cancellation_reason: str | None
    closed_at: datetime | None
    branch_name: str
    branch_gstin: str
    branch_state_code: str
    company_registered_address: str | None
    pickup_address: str | None
    supplier_name: str
    supplier_gstin: str | None
    supplier_pan: str | None
    supplier_email: str | None
    supplier_phone: str | None
    supplier_address_line1: str
    supplier_address_line2: str | None
    supplier_city: str
    supplier_state: str
    supplier_state_code: str
    supplier_postal_code: str
    purchaser_name: str | None
    purchaser_gstin: str | None
    purchaser_pan: str | None
    purchaser_email: str | None
    purchaser_phone: str | None
    purchaser_address_line1: str | None
    purchaser_address_line2: str | None
    purchaser_city: str | None
    purchaser_state: str | None
    purchaser_state_code: str | None
    purchaser_postal_code: str | None
    freight_charges: Decimal
    packing_charges: Decimal
    other_charges: Decimal
    discount_amount: Decimal
    taxable_value: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    unrounded_total: Decimal
    round_off: Decimal
    final_total: Decimal
    amount_in_words: str
    pdf_sha256: str | None
    pdf_template_version: str | None
    pdf_storage_key: str | None
    pdf_generated_by_id: int | None
    pdf_generated_at: datetime | None
    lines: list[PurchaseOrderLineRead]

    @field_serializer(
        "freight_charges",
        "packing_charges",
        "other_charges",
        "discount_amount",
        "taxable_value",
        "cgst_amount",
        "sgst_amount",
        "igst_amount",
        "cess_amount",
        "unrounded_total",
        "round_off",
        "final_total",
    )
    def serialize_decimal_fields(self, value: Decimal) -> str:
        return serialize_decimal(value)


class PurchaseOrderUpdate(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)
    purchase_order_number: str | None = Field(default=None, max_length=100)
    expected_delivery_date: date | None = None
    payment_terms: str | None = Field(default=None, max_length=255)
    # Full draft changes reuse the creation validators. The persisted type and
    # supplier identity cannot change; an issued PO number remains immutable.
    reagent_details: PurchaseOrderCreate | None = None
    domestic_details: PurchaseOrderCreate | None = None

    @field_validator("purchase_order_number", mode="before")
    @classmethod
    def validate_purchase_order_number(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("PO No. cannot be null")
        return normalize_purchase_order_number(value)


class PurchaseOrderWorkflowAction(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)


class PurchaseOrderReasonAction(PurchaseOrderWorkflowAction):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Reason is required")
        return value


class PurchaseOrderRegisterPage(BaseModel):
    items: list[PurchaseOrderRead]
    total: int
    page: int
    page_size: int
