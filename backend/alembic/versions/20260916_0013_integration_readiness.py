"""Provider-agnostic accounting and GST integration boundary."""

import sqlalchemy as sa
from alembic import op


revision = "20260916_0013"
down_revision = "20260916_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "outbound_integration_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider_key", sa.String(80), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), server_default="unavailable", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("locked_at", sa.DateTime(timezone=True)),
        sa.Column("external_reference", sa.String(255)),
        sa.Column("external_status", sa.String(50)),
        sa.Column("external_submitted_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("last_error_message", sa.Text()),
        sa.Column("request_snapshot", sa.JSON(), nullable=False),
        sa.Column("response_snapshot", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("branch_id", "idempotency_key", name="uq_outbound_job_scope_key"),
    )
    op.create_index("ix_outbound_jobs_branch_status", "outbound_integration_jobs", ["branch_id", "status", "created_at"])
    op.create_index("ix_outbound_jobs_invoice", "outbound_integration_jobs", ["invoice_id", "provider_key", "operation"])

    op.create_table(
        "integration_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("outbound_integration_jobs.id"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("before", sa.JSON()),
        sa.Column("after", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.create_table(
        "integration_reconciliations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_id", sa.Integer(), sa.ForeignKey("outbound_integration_jobs.id"), nullable=False),
        sa.Column("difference_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), server_default="open", nullable=False),
        sa.Column("local_status", sa.String(20), nullable=False),
        sa.Column("external_status", sa.String(50)),
        sa.Column("external_reference", sa.String(255)),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("resolution_note", sa.Text()),
    )
    op.create_index("ix_integration_reconciliation_open", "integration_reconciliations", ["status", "detected_at"])
    op.create_index("ix_integration_reconciliation_job", "integration_reconciliations", ["job_id", "detected_at"])


def downgrade():
    raise RuntimeError("Integration audit history is forward-only")
