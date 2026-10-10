from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Date, DateTime, Enum as SAEnum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.enums import InvoiceStatus
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.company import Branch
    from app.models.master_records import BankAccount
    from app.models.master_records import Product
    from app.models.user import User


def invoice_status_column(default: InvoiceStatus | None = None, nullable: bool | None = None):
    return mapped_column(
        SAEnum(
            InvoiceStatus,
            name="invoice_status",
            native_enum=False,
            validate_strings=True,
            values_callable=lambda statuses: [status.value for status in statuses],
            create_constraint=False,
        ),
        default=default,
        nullable=default is None if nullable is None else nullable,
    )


class Invoice(TimestampMixin, Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    buyer_customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    consignee_customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id"))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id", name="fk_invoices_supplier"), index=True)
    transporter_id: Mapped[int | None] = mapped_column(ForeignKey("transporters.id"))
    terms_and_conditions_id: Mapped[int | None] = mapped_column(ForeignKey("terms_and_conditions.id"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    pdf_generated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    status: Mapped[InvoiceStatus] = invoice_status_column(InvoiceStatus.DRAFT)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    submitted_revision: Mapped[int | None] = mapped_column(Integer)
    approved_revision: Mapped[int | None] = mapped_column(Integer)
    returned_reason: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[str] = mapped_column(String(20), default="sales", server_default="sales", nullable=False)
    invoice_number: Mapped[str | None] = mapped_column(String(80), unique=True)
    invoice_sequence: Mapped[int | None] = mapped_column(Integer)
    financial_year: Mapped[str | None] = mapped_column(String(7))
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR", server_default="INR")
    delivery_note_date: Mapped[date | None] = mapped_column(Date)
    place_of_supply_state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    po_number: Mapped[str | None] = mapped_column(String(100))
    po_date: Mapped[date | None] = mapped_column(Date)
    payment_terms: Mapped[str | None] = mapped_column(String(255))
    due_date: Mapped[date | None] = mapped_column(Date)
    irn: Mapped[str | None] = mapped_column(String(100))
    signed_qr_data: Mapped[str | None] = mapped_column(Text)
    e_way_bill_number: Mapped[str | None] = mapped_column(String(50))
    e_way_bill_date: Mapped[date | None] = mapped_column(Date)
    acknowledgement_number: Mapped[str | None] = mapped_column(String(50))
    acknowledgement_date: Mapped[date | None] = mapped_column(Date)
    transport_mode: Mapped[str | None] = mapped_column(String(100))
    vehicle_number: Mapped[str | None] = mapped_column(String(30))
    vehicle_type: Mapped[str | None] = mapped_column(String(100))
    lr_number: Mapped[str | None] = mapped_column(String(100))
    lr_date: Mapped[date | None] = mapped_column(Date)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date)

    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    branch_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    branch_state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    seller_legal_name: Mapped[str | None] = mapped_column(String(255))
    seller_trade_name: Mapped[str | None] = mapped_column(String(255))
    seller_logo_data_uri: Mapped[str | None] = mapped_column(Text)
    seller_pan: Mapped[str | None] = mapped_column(String(10))
    company_registered_address: Mapped[str | None] = mapped_column(Text)
    pickup_address: Mapped[str | None] = mapped_column(Text)
    seller_address_line1: Mapped[str | None] = mapped_column(String(255))
    seller_address_line2: Mapped[str | None] = mapped_column(String(255))
    seller_city: Mapped[str | None] = mapped_column(String(100))
    seller_state: Mapped[str | None] = mapped_column(String(100))
    seller_postal_code: Mapped[str | None] = mapped_column(String(20))
    seller_phone: Mapped[str | None] = mapped_column(String(30))
    seller_email: Mapped[str | None] = mapped_column(String(255))
    seller_email_addresses: Mapped[list[str] | None] = mapped_column(JSON)
    buyer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer_gstin: Mapped[str | None] = mapped_column(String(15))
    buyer_pan: Mapped[str | None] = mapped_column(String(10))
    buyer_email: Mapped[str | None] = mapped_column(String(255))
    buyer_phone: Mapped[str | None] = mapped_column(String(30))
    buyer_address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    buyer_address_line2: Mapped[str | None] = mapped_column(String(255))
    buyer_city: Mapped[str] = mapped_column(String(100), nullable=False)
    buyer_state: Mapped[str] = mapped_column(String(100), nullable=False)
    buyer_state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    buyer_postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    consignee_name: Mapped[str | None] = mapped_column(String(255))
    consignee_gstin: Mapped[str | None] = mapped_column(String(15))
    consignee_pan: Mapped[str | None] = mapped_column(String(10))
    consignee_email: Mapped[str | None] = mapped_column(String(255))
    consignee_phone: Mapped[str | None] = mapped_column(String(30))
    consignee_address_line1: Mapped[str | None] = mapped_column(String(255))
    consignee_address_line2: Mapped[str | None] = mapped_column(String(255))
    consignee_city: Mapped[str | None] = mapped_column(String(100))
    consignee_state: Mapped[str | None] = mapped_column(String(100))
    consignee_state_code: Mapped[str | None] = mapped_column(String(2))
    consignee_postal_code: Mapped[str | None] = mapped_column(String(20))
    bank_name: Mapped[str | None] = mapped_column(String(255))
    bank_account_name: Mapped[str | None] = mapped_column(String(255))
    bank_account_number: Mapped[str | None] = mapped_column(String(50))
    bank_ifsc_code: Mapped[str | None] = mapped_column(String(20))
    bank_branch_name: Mapped[str | None] = mapped_column(String(255))
    transporter_name: Mapped[str | None] = mapped_column(String(255))
    transporter_gstin: Mapped[str | None] = mapped_column(String(15))
    terms_title: Mapped[str | None] = mapped_column(String(255))
    terms_body: Mapped[str | None] = mapped_column(Text)

    freight_charges: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    packing_charges: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    other_charges: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    taxable_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    cess_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    unrounded_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    round_off: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    final_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    amount_in_words: Mapped[str] = mapped_column(String(500), nullable=False)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pdf_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    pdf_template_version: Mapped[str | None] = mapped_column(String(50))
    pdf_storage_key: Mapped[str | None] = mapped_column(String(500))

    branch: Mapped[Branch] = relationship()
    bank_account: Mapped[BankAccount | None] = relationship()
    lines: Mapped[list[InvoiceLine]] = relationship(back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.sort_order")
    audit_logs: Mapped[list[InvoiceAuditLog]] = relationship(back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceAuditLog.id")
    revisions: Mapped[list[InvoiceRevision]] = relationship(back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceRevision.id")


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    manufacturer_name: Mapped[str | None] = mapped_column(String(255))
    manufacturer_code: Mapped[str | None] = mapped_column(String(30))
    manufacturer_product_code: Mapped[str | None] = mapped_column(String(100))
    part_no: Mapped[str | None] = mapped_column(String(100))
    pack_size: Mapped[str | None] = mapped_column(String(100))
    hsn_sac: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    other_charge: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    taxable_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cess_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cess_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()


class InvoiceAuditLog(Base):
    __tablename__ = "invoice_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    from_status: Mapped[InvoiceStatus | None] = invoice_status_column()
    to_status: Mapped[InvoiceStatus] = invoice_status_column(nullable=False)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="audit_logs")
    actor: Mapped[User] = relationship()


class InvoiceRevision(Base):
    __tablename__ = "invoice_revisions"
    __table_args__ = (UniqueConstraint("invoice_id", "revision", name="uq_invoice_revision"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="revisions")
    actor: Mapped[User] = relationship()


class InvoiceNumberCounter(Base):
    __tablename__ = "invoice_number_counters"
    __table_args__ = (UniqueConstraint("branch_id", "financial_year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    financial_year: Mapped[str] = mapped_column(String(7), nullable=False)
    next_sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class InvoiceCreationRequest(TimestampMixin, Base):
    __tablename__ = "invoice_creation_requests"
    __table_args__ = (
        UniqueConstraint("branch_id", "idempotency_key", name="uq_invoice_creation_branch_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), unique=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
