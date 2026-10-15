"""A working correction never mutates the live confirmed financial document."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class BillCorrection(Base):
    __tablename__ = "bill_corrections"
    __table_args__ = (
        CheckConstraint("(invoice_id IS NOT NULL AND purchase_order_id IS NULL) OR (invoice_id IS NULL AND purchase_order_id IS NOT NULL)", name="ck_bill_correction_one_document"),
        CheckConstraint("status IN ('draft', 'pending_approval', 'confirmed')", name="ck_bill_correction_status"),
        Index("ix_bill_corrections_queue", "branch_id", "status", "updated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), unique=True)
    purchase_order_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"), unique=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    base_version: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    original_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    working_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

