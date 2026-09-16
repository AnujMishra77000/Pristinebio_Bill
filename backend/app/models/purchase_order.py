from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.company import Branch
    from app.models.master_records import Product, Supplier
    from app.models.user import User


class PurchaseOrder(TimestampMixin, Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    purchase_order_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date)
    payment_terms: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)

    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    branch_gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    branch_state_code: Mapped[str] = mapped_column(String(2), nullable=False)
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
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_id])
    pdf_generated_by: Mapped[User | None] = relationship(foreign_keys=[pdf_generated_by_id])
    lines: Mapped[list[PurchaseOrderLine]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderLine.sort_order",
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(ForeignKey("purchase_orders.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    sort_order: Mapped[int] = mapped_column(nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
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
