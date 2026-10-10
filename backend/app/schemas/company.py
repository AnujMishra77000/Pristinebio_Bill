from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.branch import BranchRead


class CompanyCreate(BaseModel):
    legal_name: str = Field(min_length=1, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    pan: str | None = Field(default=None, max_length=10)
    registered_address: str | None = Field(default=None, max_length=1000)
    logo_data_uri: str | None = Field(default=None, max_length=2_000_000)
    is_active: bool = True


class CompanyUpdate(BaseModel):
    legal_name: str | None = Field(default=None, min_length=1, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    pan: str | None = Field(default=None, max_length=10)
    registered_address: str | None = Field(default=None, max_length=1000)
    logo_data_uri: str | None = Field(default=None, max_length=2_000_000)
    is_active: bool | None = None


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    legal_name: str
    trade_name: str | None
    pan: str | None
    registered_address: str | None
    logo_data_uri: str | None
    is_active: bool


class SellerProfileUpsert(BaseModel):
    """Company and primary seller/GST details entered from the billing desk."""

    legal_name: str = Field(min_length=1, max_length=255)
    trade_name: str | None = Field(default=None, max_length=255)
    pan: str | None = Field(default=None, max_length=10)
    registered_address: str | None = Field(default=None, max_length=1000)
    logo_data_uri: str | None = Field(default=None, max_length=2_000_000)
    seller_name: str = Field(min_length=1, max_length=255)
    gstin: str = Field(min_length=15, max_length=15)
    address_line1: str = Field(min_length=1, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    state_code: str = Field(min_length=2, max_length=2)
    postal_code: str = Field(min_length=1, max_length=20)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    secondary_email: EmailStr | None = None
    bank_name: str | None = Field(default=None, max_length=255)
    bank_branch_name: str | None = Field(default=None, max_length=255)
    bank_account_name: str | None = Field(default=None, max_length=255)
    bank_account_number: str | None = Field(default=None, max_length=50)
    bank_ifsc_code: str | None = Field(default=None, max_length=20)
    terms_body: str | None = Field(default=None, max_length=10000)
    is_active: bool = True


class SellerProfileRead(BaseModel):
    company: CompanyRead | None
    seller_profile: BranchRead | None
