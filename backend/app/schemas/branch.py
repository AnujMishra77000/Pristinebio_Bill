from pydantic import BaseModel, ConfigDict, EmailStr, Field


class BranchCreate(BaseModel):
    company_id: int
    name: str = Field(min_length=1, max_length=255)
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


class BranchUpdate(BaseModel):
    company_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    address_line1: str | None = Field(default=None, min_length=1, max_length=255)
    address_line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    state_code: str | None = Field(default=None, min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    phone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    secondary_email: EmailStr | None = None
    bank_name: str | None = Field(default=None, max_length=255)
    bank_branch_name: str | None = Field(default=None, max_length=255)
    bank_account_name: str | None = Field(default=None, max_length=255)
    bank_account_number: str | None = Field(default=None, max_length=50)
    bank_ifsc_code: str | None = Field(default=None, max_length=20)
    terms_body: str | None = Field(default=None, max_length=10000)
    is_active: bool | None = None


class BranchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    name: str
    gstin: str
    address_line1: str
    address_line2: str | None
    city: str
    state: str
    state_code: str
    postal_code: str
    phone: str | None
    email: EmailStr | None
    secondary_email: EmailStr | None
    bank_name: str | None
    bank_branch_name: str | None
    bank_account_name: str | None
    bank_account_number: str | None
    bank_ifsc_code: str | None
    terms_body: str | None
    is_active: bool
