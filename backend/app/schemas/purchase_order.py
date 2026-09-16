from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.schemas.common import serialize_decimal
from app.schemas.master_records import SupplierCreate
from app.schemas.invoice import InvoiceLineInput


class PurchaseOrderCreate(BaseModel):
    branch_id: int | None = None
    supplier_id: int | None = None
    supplier: SupplierCreate | None = None
    order_date: date
    expected_delivery_date: date | None = None
    payment_terms: str | None = Field(default=None, max_length=255)
    freight_charges: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    packing_charges: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    other_charges: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    lines: list[InvoiceLineInput] = Field(min_length=1)


class PurchaseOrderLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    sort_order: int
    product_name: str
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
    created_by_id: int
    purchase_order_number: str
    order_date: date
    expected_delivery_date: date | None
    payment_terms: str | None
    status: str
    branch_name: str
    branch_gstin: str
    branch_state_code: str
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
