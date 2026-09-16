from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_serializer

from app.schemas.common import AddressPayload, AddressRead, serialize_decimal


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


class ProductCreate(BaseModel):
    branch_id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    hsn_sac: str = Field(min_length=1, max_length=20)
    unit: str = Field(min_length=1, max_length=50)
    base_rate: Decimal = Field(ge=Decimal("0"))
    gst_rate: Decimal = Field(ge=Decimal("0"))
    cess_rate: Decimal = Field(ge=Decimal("0"))
    is_active: bool = True


class ProductUpdate(BaseModel):
    branch_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    hsn_sac: str | None = Field(default=None, min_length=1, max_length=20)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    base_rate: Decimal | None = Field(default=None, ge=Decimal("0"))
    gst_rate: Decimal | None = Field(default=None, ge=Decimal("0"))
    cess_rate: Decimal | None = Field(default=None, ge=Decimal("0"))
    is_active: bool | None = None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    branch_id: int
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
    is_active: bool = True


class SupplierUpdate(BaseModel):
    branch_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    pan: str | None = Field(default=None, max_length=10)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)
    address: AddressPayload | None = None
    is_active: bool | None = None


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
