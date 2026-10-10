from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.company import Branch
    from app.models.master_records import Product, Purchaser, Supplier
    from app.models.user import User


class PurchaseOrder(TimestampMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint("document_type IN ('domestic_oils', 'reagent')", name="ck_purchase_order_document_type"),
        Index("ix_purchase_orders_branch_type_date", "branch_id", "document_type", "order_date", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    purchaser_id: Mapped[int | None] = mapped_column(ForeignKey("purchasers.id"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    purchase_order_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), default="domestic_oils", server_default="domestic_oils", nullable=False)
    place_of_supply_state_code: Mapped[str | None] = mapped_column(String(2))
    delivery_note_date: Mapped[date | None] = mapped_column(Date)
    po_reference_number: Mapped[str | None] = mapped_column(String(100))
    po_reference_date: Mapped[date | None] = mapped_column(Date)
    transport_mode: Mapped[str | None] = mapped_column(String(100))
    vehicle_number: Mapped[str | None] = mapped_column(String(30))
    vehicle_type: Mapped[str | None] = mapped_column(String(100))
    lr_number: Mapped[str | None] = mapped_column(String(100))
    lr_date: Mapped[date | None] = mapped_column(Date)
    consignee_details: Mapped[dict | None] = mapped_column(JSON)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date)
    payment_terms: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    submitted_revision: Mapped[int | None] = mapped_column(Integer)
    approved_revision: Mapped[int | None] = mapped_column(Integer)
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    branch_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    branch_state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    company_registered_address: Mapped[str | None] = mapped_column(Text)
    seller_email_addresses: Mapped[list[str] | None] = mapped_column(JSON)
    pickup_address: Mapped[str | None] = mapped_column(Text)
    supplier_name: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_gstin: Mapped[str | None] = mapped_column(String(15))
    supplier_pan: Mapped[str | None] = mapped_column(String(10))
    supplier_email: Mapped[str | None] = mapped_column(String(255))
    supplier_phone: Mapped[str | None] = mapped_column(String(30))
    supplier_address_line1: Mapped[str] = mapped_column(String(255), nullable=False)
    supplier_address_line2: Mapped[str | None] = mapped_column(String(255))
    supplier_city: Mapped[str] = mapped_column(String(100), nullable=False)
    supplier_state: Mapped[str] = mapped_column(String(100), nullable=False)
    supplier_state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    supplier_postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    purchaser_name: Mapped[str | None] = mapped_column(String(255))
    purchaser_gstin: Mapped[str | None] = mapped_column(String(15))
    purchaser_pan: Mapped[str | None] = mapped_column(String(10))
    purchaser_email: Mapped[str | None] = mapped_column(String(255))
    purchaser_phone: Mapped[str | None] = mapped_column(String(30))
    purchaser_address_line1: Mapped[str | None] = mapped_column(String(255))
    purchaser_address_line2: Mapped[str | None] = mapped_column(String(255))
    purchaser_city: Mapped[str | None] = mapped_column(String(100))
    purchaser_state: Mapped[str | None] = mapped_column(String(100))
    purchaser_state_code: Mapped[str | None] = mapped_column(String(2))
    purchaser_postal_code: Mapped[str | None] = mapped_column(String(20))

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

    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    pdf_template_version: Mapped[str | None] = mapped_column(String(50))
    pdf_storage_key: Mapped[str | None] = mapped_column(String(255))
    pdf_generated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    pdf_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    branch: Mapped[Branch] = relationship()
    supplier: Mapped[Supplier] = relationship()
    purchaser: Mapped[Purchaser | None] = relationship()
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    pdf_generated_by: Mapped[User | None] = relationship(foreign_keys=[pdf_generated_by_id])
    lines: Mapped[list[PurchaseOrderLine]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderLine.sort_order",
    )
    audit_logs: Mapped[list[PurchaseOrderAuditLog]] = relationship(back_populates="purchase_order", cascade="all, delete-orphan", order_by="PurchaseOrderAuditLog.id")
    revisions: Mapped[list[PurchaseOrderRevision]] = relationship(back_populates="purchase_order", cascade="all, delete-orphan", order_by="PurchaseOrderRevision.id")


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    manufacturer_id: Mapped[int | None] = mapped_column(ForeignKey("manufacturers.id"))
    manufacturer_name: Mapped[str | None] = mapped_column(String(255))
    manufacturer_code: Mapped[str | None] = mapped_column(String(30))
    manufacturer_product_code: Mapped[str | None] = mapped_column(String(100))
    part_no: Mapped[str | None] = mapped_column(String(100))
    pack_size: Mapped[str | None] = mapped_column(String(100))
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), server_default="0", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    hsn_sac: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    other_charge: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"), nullable=False)
    taxable_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    gst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cess_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cess_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()


class PurchaseOrderAuditLog(Base):
    __tablename__ = "purchase_order_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="audit_logs")
    actor: Mapped[User] = relationship()


class PurchaseOrderRevision(Base):
    __tablename__ = "purchase_order_revisions"
    __table_args__ = (UniqueConstraint("purchase_order_id", "revision", name="uq_purchase_order_revision"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="revisions")
    actor: Mapped[User] = relationship()


class PurchaseOrderCreationRequest(TimestampMixin, Base):
    __tablename__ = "purchase_order_creation_requests"
    __table_args__ = (
        UniqueConstraint("branch_id", "idempotency_key", name="uq_purchase_order_creation_branch_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"), unique=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
