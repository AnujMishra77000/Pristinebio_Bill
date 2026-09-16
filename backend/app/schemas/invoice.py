from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer

from app.models.enums import InvoiceStatus
from app.schemas.common import AddressPayload
from app.schemas.common import serialize_decimal


class InvoiceLineInput(BaseModel):
    product_id: int | None = None
    product_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    hsn_sac: str | None = Field(default=None, min_length=1, max_length=20)
    quantity: Decimal = Field(gt=Decimal("0"))
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    rate: Decimal | None = Field(default=None, ge=Decimal("0"))
    other_charge: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    discount_amount: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    gst_rate: Decimal | None = Field(default=None, ge=Decimal("0"))
    cess_rate: Decimal | None = Field(default=None, ge=Decimal("0"))


class InvoiceCustomerInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    pan: str | None = Field(default=None, max_length=10)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    billing_address: AddressPayload
    shipping_address: AddressPayload | None = None
    is_active: bool = True


class InvoiceBasePayload(BaseModel):
    branch_id: int | None = None
    buyer_customer_id: int | None = None
    buyer: InvoiceCustomerInput | None = None
    consignee_customer_id: int | None = None
    consignee: InvoiceCustomerInput | None = None
    bank_account_id: int | None = None
    invoice_date: date
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


class InvoiceCreate(InvoiceBasePayload):
    pass


class InvoicePreviewRequest(InvoiceBasePayload):
    pass


class InvoiceUpdate(BaseModel):
    buyer_customer_id: int | None = None
    consignee_customer_id: int | None = None
    bank_account_id: int | None = None
    invoice_date: date | None = None
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


class InvoiceLineRead(BaseModel):
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


class InvoicePreviewLineRead(BaseModel):
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
    transporter_id: int | None
    terms_and_conditions_id: int | None
    status: InvoiceStatus
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
