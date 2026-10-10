from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationInfo, field_serializer, field_validator

from app.schemas.common import AddressPayload, AddressRead, serialize_decimal
from app.services.financial_validation import normalize_rate, normalize_tax_rate, optional_text, required_text
from app.services.units import normalize_catalog_unit
from app.services.customer_identity import normalize_gstin


class CustomerCreate(BaseModel):
    branch_id: int | None = None
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

    @field_validator("pan", "email", "phone", mode="before")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        return optional_text(value, "Customer detail")


class CustomerUpdate(BaseModel):
    branch_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    pan: str | None = Field(default=None, max_length=10)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    billing_address: AddressPayload | None = None
    shipping_address: AddressPayload | None = None
    is_active: bool | None = None

    @field_validator("branch_id", "name", "billing_address", "is_active", mode="before")
    @classmethod
    def reject_required_null(cls, value: object, info: ValidationInfo) -> object:
        if value is None:
            raise ValueError(f"{info.field_name} must not be null; omit it to preserve its saved value")
        return value

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return required_text(value, "Customer name") if value is not None else None

    @field_validator("gstin", mode="before")
    @classmethod
    def normalize_customer_gstin(cls, value: str | None) -> str | None:
        return normalize_gstin(optional_text(value, "Customer GSTIN"))

    @field_validator("pan", "email", "phone", mode="before")
    @classmethod
    def normalize_optional_update_fields(cls, value: str | None) -> str | None:
        return optional_text(value, "Customer detail")


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: int
    name: str
    gstin: str | None
    pan: str | None
    email: EmailStr | None
    phone: str | None
    billing_address: AddressRead
    shipping_address: AddressRead | None
    is_active: bool


class ManufacturerCreate(BaseModel):
    branch_id: int | None = None
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=255)
    is_active: bool = True

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return required_text(value, "Manufacturer code").upper()

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return required_text(value, "Manufacturer name")


class ManufacturerUpdate(BaseModel):
    branch_id: int | None = None
    code: str | None = Field(default=None, min_length=1, max_length=30)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    is_active: bool | None = None

    @field_validator("code", mode="before")
    @classmethod
    def normalize_optional_code(cls, value: str | None) -> str | None:
        return required_text(value, "Manufacturer code").upper() if value is not None else None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_optional_name(cls, value: str | None) -> str | None:
        return required_text(value, "Manufacturer name") if value is not None else None


class ManufacturerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: int
    code: str
    name: str
    is_active: bool


class ProductCreate(BaseModel):
    branch_id: int | None = None
    manufacturer_id: int | None = None
    manufacturer_product_code: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    hsn_sac: str = Field(min_length=1, max_length=20)
    # Product master is intentionally catalog-only.  Reagent unit and rate are
    # transaction details, while these non-null storage defaults preserve the
    # existing database contract and backwards-compatible API clients.
    unit: str = Field(default="kg", min_length=1, max_length=50)
    base_rate: Decimal = Field(default=Decimal("0.0000"), ge=Decimal("0"))
    gst_rate: Decimal = Field(ge=Decimal("0"))
    cess_rate: Decimal = Field(ge=Decimal("0"))
    is_active: bool = True

    @field_validator("name", "hsn_sac", mode="before")
    @classmethod
    def validate_required_text_fields(cls, value: str, info: ValidationInfo) -> str:
        return required_text(value, info.field_name.replace("_", " ").title())

    @field_validator("unit", mode="before")
    @classmethod
    def validate_unit(cls, value: str) -> str:
        return normalize_catalog_unit(required_text(value, "Unit"))

    @field_validator("manufacturer_product_code", mode="before")
    @classmethod
    def normalize_product_code(cls, value: str | None) -> str | None:
        code = optional_text(value, "Manufacturer product code")
        return code.upper() if code else None

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return optional_text(value, "Product description")

    @field_validator("base_rate")
    @classmethod
    def validate_base_rate(cls, value: Decimal) -> Decimal:
        return normalize_rate(value, "Base rate")

    @field_validator("gst_rate", "cess_rate")
    @classmethod
    def validate_tax_rates(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        return normalize_tax_rate(value, info.field_name.replace("_", " ").title())


class ProductUpdate(BaseModel):
    branch_id: int | None = None
    manufacturer_id: int | None = None
    manufacturer_product_code: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    hsn_sac: str | None = Field(default=None, min_length=1, max_length=20)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    base_rate: Decimal | None = Field(default=None, ge=Decimal("0"))
    gst_rate: Decimal | None = Field(default=None, ge=Decimal("0"))
    cess_rate: Decimal | None = Field(default=None, ge=Decimal("0"))
    is_active: bool | None = None

    @field_validator("name", "hsn_sac", mode="before")
    @classmethod
    def normalize_required_update_text(cls, value: str | None, info: ValidationInfo) -> str | None:
        return required_text(value, info.field_name.replace("_", " ").title()) if value is not None else None

    @field_validator("unit", mode="before")
    @classmethod
    def normalize_optional_unit(cls, value: str | None) -> str | None:
        return normalize_catalog_unit(required_text(value, "Unit")) if value is not None else None

    @field_validator("manufacturer_product_code", mode="before")
    @classmethod
    def normalize_optional_product_code(cls, value: str | None) -> str | None:
        code = optional_text(value, "Manufacturer product code")
        return code.upper() if code else None

    @field_validator("description", mode="before")
    @classmethod
    def normalize_update_description(cls, value: str | None) -> str | None:
        return optional_text(value, "Product description")

    @field_validator("base_rate")
    @classmethod
    def validate_optional_base_rate(cls, value: Decimal | None) -> Decimal | None:
        return normalize_rate(value, "Base rate") if value is not None else None

    @field_validator("gst_rate", "cess_rate")
    @classmethod
    def validate_optional_tax_rates(cls, value: Decimal | None, info: ValidationInfo) -> Decimal | None:
        return normalize_tax_rate(value, info.field_name.replace("_", " ").title()) if value is not None else None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: int
    manufacturer_id: int | None
    manufacturer_code: str | None
    manufacturer_name: str | None
    manufacturer_product_code: str | None
    name: str
    description: str | None
    hsn_sac: str
    unit: str
    base_rate: Decimal
    gst_rate: Decimal
    cess_rate: Decimal
    is_active: bool

    @field_serializer("base_rate", "gst_rate", "cess_rate")
    def serialize_rate(self, value: Decimal) -> str:
        return serialize_decimal(value)


class SupplierCreate(BaseModel):
    branch_id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    pan: str | None = Field(default=None, max_length=10)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    address: AddressPayload
    is_default: bool = False
    is_active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return required_text(value, "Supplier name")

    @field_validator("gstin", "pan", "email", "phone", mode="before")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        return optional_text(value, "Supplier detail")


class SupplierUpdate(BaseModel):
    branch_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    pan: str | None = Field(default=None, max_length=10)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    address: AddressPayload | None = None
    is_default: bool | None = None
    is_active: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return required_text(value, "Supplier name") if value is not None else None

    @field_validator("gstin", "pan", "email", "phone", mode="before")
    @classmethod
    def normalize_optional_update_fields(cls, value: str | None) -> str | None:
        return optional_text(value, "Supplier detail")


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: int
    name: str
    gstin: str | None
    pan: str | None
    email: EmailStr | None
    phone: str | None
    address: AddressRead
    is_default: bool
    is_active: bool


class PurchaserCreate(BaseModel):
    branch_id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    pan: str | None = Field(default=None, max_length=10)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    address: AddressPayload
    is_active: bool = True

    @field_validator("name", mode="before")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return required_text(value, "Purchaser name")

    @field_validator("gstin", "pan", "email", "phone", mode="before")
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        return optional_text(value, "Purchaser detail")


class PurchaserUpdate(BaseModel):
    branch_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    pan: str | None = Field(default=None, max_length=10)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    address: AddressPayload | None = None
    is_active: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return required_text(value, "Purchaser name") if value is not None else None

    @field_validator("gstin", "pan", "email", "phone", mode="before")
    @classmethod
    def normalize_optional_update_fields(cls, value: str | None) -> str | None:
        return optional_text(value, "Purchaser detail")


class PurchaserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: int
    name: str
    gstin: str | None
    pan: str | None
    email: EmailStr | None
    phone: str | None
    address: AddressRead
    is_active: bool


class BankAccountCreate(BaseModel):
    branch_id: int
    bank_name: str = Field(min_length=1, max_length=255)
    account_name: str = Field(min_length=1, max_length=255)
    account_number: str = Field(min_length=1, max_length=50)
    ifsc_code: str = Field(min_length=1, max_length=20)
    branch_name: str | None = Field(default=None, max_length=255)
    is_default: bool = False
    is_active: bool = True


class BankAccountUpdate(BaseModel):
    branch_id: int | None = None
    bank_name: str | None = Field(default=None, min_length=1, max_length=255)
    account_name: str | None = Field(default=None, min_length=1, max_length=255)
    account_number: str | None = Field(default=None, min_length=1, max_length=50)
    ifsc_code: str | None = Field(default=None, min_length=1, max_length=20)
    branch_name: str | None = Field(default=None, max_length=255)
    is_default: bool | None = None
    is_active: bool | None = None


class BankAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: int
    bank_name: str
    account_name: str
    account_number: str
    ifsc_code: str
    branch_name: str | None
    is_default: bool
    is_active: bool


class TransporterCreate(BaseModel):
    branch_id: int
    name: str = Field(min_length=1, max_length=255)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    phone: str | None = Field(default=None, max_length=30)
    vehicle_number: str | None = Field(default=None, max_length=30)
    is_active: bool = True


class TransporterUpdate(BaseModel):
    branch_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    phone: str | None = Field(default=None, max_length=30)
    vehicle_number: str | None = Field(default=None, max_length=30)
    is_active: bool | None = None


class TransporterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: int
    name: str
    gstin: str | None
    phone: str | None
    vehicle_number: str | None
    is_active: bool


class TermsCreate(BaseModel):
    branch_id: int
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    is_default: bool = False
    is_active: bool = True


class TermsUpdate(BaseModel):
    branch_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = Field(default=None, min_length=1)
    is_default: bool | None = None
    is_active: bool | None = None


class TermsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: int
    title: str
    body: str
    is_default: bool
    is_active: bool
