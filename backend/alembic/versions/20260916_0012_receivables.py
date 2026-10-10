"""Receipts, allocation ledger, credit controls and invoice currency."""
import sqlalchemy as sa
from alembic import op

revision = "20260916_0012"
down_revision = "20260916_0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("currency", sa.String(3), server_default="INR", nullable=False))
    op.create_table("receipts",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False), sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("receipt_number", sa.String(80), nullable=False), sa.Column("receipt_date", sa.Date(), nullable=False), sa.Column("currency", sa.String(3), server_default="INR", nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False), sa.Column("reference", sa.String(255)), sa.Column("notes", sa.Text()),
        sa.Column("status", sa.String(20), server_default="posted", nullable=False), sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("reversed_at", sa.DateTime(timezone=True)), sa.Column("reversed_by_id", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("reversal_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("branch_id", "receipt_number", name="uq_receipt_branch_number"),
    )
    op.create_table("receipt_allocations",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("receipts.id"), nullable=False),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False), sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("reversed_at", sa.DateTime(timezone=True)),
        sa.Column("reversed_by_id", sa.Integer(), sa.ForeignKey("users.id")), sa.Column("reversal_reason", sa.Text()),
    )
    op.create_table("payment_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False), sa.Column("entity_id", sa.Integer(), nullable=False), sa.Column("action", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text()), sa.Column("before", sa.JSON()), sa.Column("after", sa.JSON()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table("payment_idempotency",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("operation", sa.String(30), nullable=False), sa.Column("idempotency_key", sa.String(255), nullable=False), sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("receipt_id", sa.Integer(), sa.ForeignKey("receipts.id"), unique=True), sa.Column("allocation_id", sa.Integer(), sa.ForeignKey("receipt_allocations.id"), unique=True),
        sa.UniqueConstraint("branch_id", "operation", "idempotency_key", name="uq_payment_idempotency_scope_key"),
    )
    op.create_table("customer_credit_limits",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False), sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("currency", sa.String(3), server_default="INR", nullable=False), sa.Column("limit_amount", sa.Numeric(14, 2), nullable=False), sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("branch_id", "customer_id", name="uq_customer_credit_limit"),
    )
    op.create_table("credit_limit_overrides",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False), sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("amount", sa.Numeric(14, 2), nullable=False), sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_receipts_branch_customer_date", "receipts", ["branch_id", "customer_id", "receipt_date"])
    op.create_index("ix_allocations_invoice", "receipt_allocations", ["invoice_id", "created_at"])
    op.create_index("ix_payment_audit_entity", "payment_audit_logs", ["entity_type", "entity_id", "created_at"])
    op.create_index("ix_credit_overrides_customer", "credit_limit_overrides", ["branch_id", "customer_id", "created_at"])


def downgrade():
    raise RuntimeError("Receivables history is forward-only")
