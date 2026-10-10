from datetime import date, datetime
from decimal import Decimal
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationInfo, field_serializer, field_validator, model_validator

from app.models.enums import InvoiceStatus
from app.schemas.common import AddressPayload
from app.schemas.common import serialize_decimal
from app.schemas.master_records import CustomerCreate
from app.services.financial_validation import (
    normalize_money,
    normalize_quantity,
    normalize_rate,
    normalize_tax_rate,
    optional_text,
    required_text,
    state_code,
)
from app.services.units import canonical_unit
from app.services.customer_identity import normalize_gstin


def _normalize_invoice_number_suffix(value: str) -> str:
    suffix = required_text(value, "Invoice number").upper()
    if re.fullmatch(r"[A-Z0-9][A-Z0-9/-]{0,29}", suffix) is None:
        raise ValueError("Invoice number must contain 1–30 letters, digits, hyphens or slashes")
    return suffix


class InvoiceLineInput(BaseModel):
    product_id: int | None = None
    manufacturer_id: int | None = None
    manufacturer_product_code: str | None = Field(default=None, max_length=100)
    product_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    part_no: str | None = Field(default=None, max_length=100)
    pack_size: str | None = Field(default=None, max_length=100)
    hsn_sac: str | None = Field(default=None, min_length=1, max_length=20)
    quantity: Decimal = Field(gt=Decimal("0"))
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    rate: Decimal | None = Field(default=None, ge=Decimal("0"))
    other_charge: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    discount_percent: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"), le=Decimal("100"))
    gst_rate: Decimal | None = Field(default=None, ge=Decimal("0"))
    cess_rate: Decimal | None = Field(default=None, ge=Decimal("0"))

    @field_validator("product_name", "description", "part_no", "hsn_sac", mode="before")
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None, info: ValidationInfo) -> str | None:
        return optional_text(value, f"Line {info.field_name}")

    @field_validator("pack_size", mode="before")
    @classmethod
    def normalize_pack_size(cls, value: str | None) -> str | None:
        value = optional_text(value, "Pack/Size")
        if value is not None and not value.isprintable():
            raise ValueError("Pack/Size must be a single line without control characters")
        return value

    @field_validator("manufacturer_product_code", mode="before")
    @classmethod
    def normalize_manufacturer_product_code(cls, value: str | None) -> str | None:
        code = optional_text(value, "Manufacturer product code")
        return code.upper() if code else None

    @field_validator("unit", mode="before")
    @classmethod
    def normalize_line_unit(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text_value = optional_text(value, "Line unit")
        if text_value is None:
            return None
        return canonical_unit(text_value) or text_value

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: Decimal) -> Decimal:
        return normalize_quantity(value)

    @field_validator("rate")
    @classmethod
    def validate_rate(cls, value: Decimal | None) -> Decimal | None:
        return normalize_rate(value) if value is not None else None

    @field_validator("other_charge", "discount_amount")
    @classmethod
    def validate_money_fields(cls, value: Decimal) -> Decimal:
        return normalize_money(value, "Line amount")

    @field_validator("gst_rate", "cess_rate", "discount_percent")
    @classmethod
    def validate_tax_fields(cls, value: Decimal | None, info: ValidationInfo) -> Decimal | None:
        return normalize_tax_rate(value, info.field_name) if value is not None else None


class InvoiceCustomerInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    pan: str | None = Field(default=None, max_length=10)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    billing_address: AddressPayload
    shipping_address: AddressPayload | None = None
    is_active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return required_text(value, "Customer name")

    @field_validator("gstin", mode="before")
    @classmethod
    def normalize_customer_gstin(cls, value: str | None) -> str | None:
        return normalize_gstin(optional_text(value, "Customer GSTIN"))

    @field_validator("pan", "phone", mode="before")
    @classmethod
    def normalize_optional_identity_fields(cls, value: str | None) -> str | None:
        return optional_text(value, "Customer detail")


class InvoiceBasePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["sales", "reagent"] = "sales"
    branch_id: int | None = None
    buyer_customer_id: int | None = None
    buyer: InvoiceCustomerInput | None = None
    consignee_customer_id: int | None = None
    consignee: InvoiceCustomerInput | None = None
    bank_account_id: int | None = None
    supplier_id: int | None = Field(default=None, ge=1, strict=True)
    invoice_date: date
    invoice_number_suffix: str | None = Field(default=None, max_length=30)
    delivery_note_date: date | None = None
    place_of_supply_state_code: str = Field(min_length=2, max_length=2)
    po_number: str | None = Field(default=None, max_length=100)
    po_date: date | None = None
    payment_terms: str | None = Field(default=None, max_length=255)
    due_date: date | None = None
    irn: str | None = Field(default=None, max_length=100)
    signed_qr_data: str | None = Field(default=None, max_length=2_000_000)
    e_way_bill_number: str | None = Field(default=None, max_length=50)
    e_way_bill_date: date | None = None
    acknowledgement_number: str | None = Field(default=None, max_length=50)
    acknowledgement_date: date | None = None
    transport_mode: str | None = Field(default=None, max_length=100)
    transporter_id: int | None = None
    vehicle_number: str | None = Field(default=None, max_length=30)
    vehicle_type: str | None = Field(default=None, max_length=100)
    lr_number: str | None = Field(default=None, max_length=100)
    lr_date: date | None = None
    expected_delivery_date: date | None = None
    freight_charges: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    packing_charges: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    other_charges: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    terms_and_conditions_id: int | None = None
    lines: list[InvoiceLineInput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reagent_units(self):
        if self.document_type == "reagent":
            for index, line in enumerate(self.lines, start=1):
                if line.unit is not None and canonical_unit(line.unit) is None:
                    raise ValueError(f"Line {index} unit must be one of: g, kg, mg, µg, mL, L, t")
        return self

    @field_validator("invoice_number_suffix", mode="before")
    @classmethod
    def normalize_invoice_number_suffix(cls, value: str | None) -> str | None:
        return _normalize_invoice_number_suffix(value) if value is not None else None

    @field_validator("place_of_supply_state_code", mode="before")
    @classmethod
    def validate_place_of_supply_state_code(cls, value: str) -> str:
        return state_code(value, "Place of supply state code")

    @field_validator("po_number", "payment_terms", "irn", "e_way_bill_number", "acknowledgement_number", "transport_mode", "vehicle_number", "vehicle_type", "lr_number", mode="before")
    @classmethod
    def normalize_optional_document_text(cls, value: str | None) -> str | None:
        return optional_text(value, "Document field")

    @field_validator("freight_charges", "packing_charges", "other_charges", "discount_amount")
    @classmethod
    def validate_document_money(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        return normalize_money(value, info.field_name.replace("_", " ").title())


class InvoiceCreate(InvoiceBasePayload):
    invoice_number_suffix: str = Field(min_length=1, max_length=30)


class InvoicePreviewRequest(InvoiceBasePayload):
    pass


class PdfPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1, strict=True)


class InvoiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int | None = Field(default=None, ge=1)
    branch_id: int | None = None
    buyer_customer_id: int | None = None
    buyer: CustomerCreate | None = None
    consignee_customer_id: int | None = None
    consignee: CustomerCreate | None = None
    bank_account_id: int | None = None
    supplier_id: int | None = Field(default=None, ge=1, strict=True)
    invoice_date: date | None = None
    invoice_number_suffix: str | None = Field(default=None, max_length=30)
    delivery_note_date: date | None = None
    place_of_supply_state_code: str | None = Field(default=None, min_length=2, max_length=2)
    po_number: str | None = Field(default=None, max_length=100)
    po_date: date | None = None
    payment_terms: str | None = Field(default=None, max_length=255)
    due_date: date | None = None
    irn: str | None = Field(default=None, max_length=100)
    signed_qr_data: str | None = Field(default=None, max_length=2_000_000)
    e_way_bill_number: str | None = Field(default=None, max_length=50)
    e_way_bill_date: date | None = None
    acknowledgement_number: str | None = Field(default=None, max_length=50)
    acknowledgement_date: date | None = None
    transport_mode: str | None = Field(default=None, max_length=100)
    transporter_id: int | None = None
    vehicle_number: str | None = Field(default=None, max_length=30)
    vehicle_type: str | None = Field(default=None, max_length=100)
    lr_number: str | None = Field(default=None, max_length=100)
    lr_date: date | None = None
    expected_delivery_date: date | None = None
    freight_charges: Decimal | None = Field(default=None, ge=Decimal("0"))
    packing_charges: Decimal | None = Field(default=None, ge=Decimal("0"))
    other_charges: Decimal | None = Field(default=None, ge=Decimal("0"))
    discount_amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    terms_and_conditions_id: int | None = None
    lines: list[InvoiceLineInput] | None = Field(default=None, min_length=1)

    @field_validator("invoice_number_suffix", mode="before")
    @classmethod
    def normalize_invoice_number_suffix(cls, value: str | None) -> str:
        return _normalize_invoice_number_suffix(value)

    @field_validator("place_of_supply_state_code", mode="before")
    @classmethod
    def validate_optional_place_of_supply_state_code(cls, value: str | None) -> str | None:
        return state_code(value, "Place of supply state code") if value is not None else None

    @field_validator("po_number", "payment_terms", "irn", "e_way_bill_number", "acknowledgement_number", "transport_mode", "vehicle_number", "vehicle_type", "lr_number", mode="before")
    @classmethod
    def normalize_optional_update_text(cls, value: str | None) -> str | None:
        return optional_text(value, "Document field")

    @field_validator("freight_charges", "packing_charges", "other_charges", "discount_amount")
    @classmethod
    def validate_optional_document_money(cls, value: Decimal | None, info: ValidationInfo) -> Decimal | None:
        return normalize_money(value, info.field_name.replace("_", " ").title()) if value is not None else None


class InvoiceLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    sort_order: int
    product_name: str
    description: str
    manufacturer_name: str | None
    manufacturer_code: str | None
    manufacturer_product_code: str | None
    part_no: str | None
    pack_size: str | None = None
    hsn_sac: str
    quantity: Decimal
    unit: str
    rate: Decimal
    other_charge: Decimal
    discount_amount: Decimal
    discount_percent: Decimal
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


class InvoicePreviewLineRead(BaseModel):
    description: str
    manufacturer_name: str | None
    manufacturer_code: str | None
    manufacturer_product_code: str | None
    part_no: str | None
    pack_size: str | None = None
    hsn_sac: str
    quantity: Decimal
    unit: str
    rate: Decimal
    other_charge: Decimal
    discount_amount: Decimal
    discount_percent: Decimal
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


class InvoicePreviewRead(BaseModel):
    lines: list[InvoicePreviewLineRead]
    taxable_value: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    cess_amount: Decimal
    unrounded_total: Decimal
    round_off: Decimal
    final_total: Decimal
    amount_in_words: str

    @field_serializer(
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


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: int
    buyer_customer_id: int
    consignee_customer_id: int | None
    bank_account_id: int | None
    supplier_id: int | None
    transporter_id: int | None
    terms_and_conditions_id: int | None
    document_type: Literal["sales", "reagent"]
    status: InvoiceStatus
    version: int
    submitted_revision: int | None
    approved_revision: int | None
    returned_reason: str | None
    invoice_number: str | None
    invoice_sequence: int | None
    financial_year: str | None
    invoice_date: date
    delivery_note_date: date | None
    place_of_supply_state_code: str
    po_number: str | None
    po_date: date | None
    payment_terms: str | None
    due_date: date | None
    irn: str | None
    signed_qr_data: str | None
    e_way_bill_number: str | None
    e_way_bill_date: date | None
    acknowledgement_number: str | None
    acknowledgement_date: date | None
    transport_mode: str | None
    vehicle_number: str | None
    vehicle_type: str | None
    lr_number: str | None
    lr_date: date | None
    expected_delivery_date: date | None
    branch_name: str
    branch_gstin: str
    branch_state_code: str
    buyer_name: str
    buyer_gstin: str | None
    buyer_pan: str | None
    buyer_email: str | None
    buyer_phone: str | None
    seller_legal_name: str | None
    seller_trade_name: str | None
    seller_logo_data_uri: str | None
    seller_pan: str | None
    company_registered_address: str | None
    pickup_address: str | None
    seller_address_line1: str | None
    seller_address_line2: str | None
    seller_city: str | None
    seller_state: str | None
    seller_postal_code: str | None
    seller_phone: str | None
    seller_email: str | None
    buyer_address_line1: str
    buyer_address_line2: str | None
    buyer_city: str
    buyer_state: str
    buyer_state_code: str
    buyer_postal_code: str
    consignee_name: str | None
    consignee_gstin: str | None
    consignee_pan: str | None
    consignee_email: str | None
    consignee_phone: str | None
    consignee_address_line1: str | None
    consignee_address_line2: str | None
    consignee_city: str | None
    consignee_state: str | None
    consignee_state_code: str | None
    consignee_postal_code: str | None
    bank_name: str | None
    bank_account_name: str | None
    bank_account_number: str | None
    bank_ifsc_code: str | None
    bank_branch_name: str | None
    transporter_name: str | None
    transporter_gstin: str | None
    terms_title: str | None
    terms_body: str | None
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
    pdf_generated_by_id: int | None
    submitted_at: datetime | None
    approved_at: datetime | None
    pdf_generated_at: datetime | None
    pdf_sha256: str | None
    pdf_template_version: str | None
    pdf_storage_key: str | None
    lines: list[InvoiceLineRead]

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


class InvoiceAuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    from_status: InvoiceStatus | None
    to_status: InvoiceStatus
    actor_user_id: int
    note: str | None
    created_at: datetime


class WorkflowAction(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)


class ReturnForCorrection(WorkflowAction):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Reason is required")
        return value


class RegisterPage(BaseModel):
    items: list[InvoiceRead]
    total: int
    page: int
    page_size: int
