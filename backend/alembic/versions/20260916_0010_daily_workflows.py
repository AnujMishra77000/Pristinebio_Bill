"""Revision-safe invoice and purchase-order operational workflows."""

import sqlalchemy as sa
from alembic import op


revision = "20260916_0010"
down_revision = "20260916_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("invoices", sa.Column("submitted_revision", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("approved_revision", sa.Integer(), nullable=True))
    op.add_column("invoices", sa.Column("returned_reason", sa.Text(), nullable=True))
    op.create_table(
        "invoice_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("invoice_id", "revision", name="uq_invoice_revision"),
    )
    op.add_column("purchase_orders", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("purchase_orders", sa.Column("submitted_revision", sa.Integer(), nullable=True))
    op.add_column("purchase_orders", sa.Column("approved_revision", sa.Integer(), nullable=True))
    op.add_column("purchase_orders", sa.Column("submitted_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("purchase_orders", sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("purchase_orders", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("purchase_orders", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("purchase_orders", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.add_column("purchase_orders", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "purchase_order_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id"), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table(
        "purchase_order_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=40), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("purchase_order_id", "revision", name="uq_purchase_order_revision"),
    )


def downgrade():
    raise RuntimeError("Daily workflow history is forward-only; do not discard transaction audit history")
