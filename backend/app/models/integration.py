from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.company import Branch
    from app.models.invoice import Invoice
    from app.models.user import User


class OutboundIntegrationJob(TimestampMixin, Base):
    """Durable boundary for a future accounting/GST provider submission."""

    __tablename__ = "outbound_integration_jobs"
    __table_args__ = (
        UniqueConstraint(
            "branch_id", "idempotency_key",
            name="uq_outbound_job_scope_key",
        ),
        Index("ix_outbound_jobs_branch_status", "branch_id", "status", "created_at"),
        Index("ix_outbound_jobs_invoice", "invoice_id", "provider_key", "operation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(80), nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unavailable", server_default="unavailable")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_reference: Mapped[str | None] = mapped_column(String(255))
    external_status: Mapped[str | None] = mapped_column(String(50))
    external_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    request_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_snapshot: Mapped[dict | None] = mapped_column(JSON)

    branch: Mapped[Branch] = relationship()
    invoice: Mapped[Invoice] = relationship()
    created_by: Mapped[User] = relationship()
    audit_logs: Mapped[list[IntegrationAuditLog]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="IntegrationAuditLog.id"
    )


class IntegrationAuditLog(Base):
    __tablename__ = "integration_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("outbound_integration_jobs.id"), nullable=False)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    job: Mapped[OutboundIntegrationJob] = relationship(back_populates="audit_logs")
    actor: Mapped[User] = relationship()


class IntegrationReconciliation(Base):
    __tablename__ = "integration_reconciliations"
    __table_args__ = (
        Index("ix_integration_reconciliation_open", "status", "detected_at"),
        Index("ix_integration_reconciliation_job", "job_id", "detected_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("outbound_integration_jobs.id"), nullable=False)
    difference_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", server_default="open")
    local_status: Mapped[str] = mapped_column(String(20), nullable=False)
    external_status: Mapped[str | None] = mapped_column(String(50))
    external_reference: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolution_note: Mapped[str | None] = mapped_column(Text)

    job: Mapped[OutboundIntegrationJob] = relationship()
    resolved_by: Mapped[User | None] = relationship()
