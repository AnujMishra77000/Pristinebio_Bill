"""Stage corrections separately; preserve every existing confirmed document.

Revision ID: 20261015_0025
Revises: 20261007_0024
"""
from alembic import op
import sqlalchemy as sa

revision = "20261015_0025"
down_revision = "20261007_0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bill_corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id", ondelete="CASCADE"), unique=True),
        sa.Column("purchase_order_id", sa.Integer(), sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), unique=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("original_snapshot", sa.JSON(), nullable=False),
        sa.Column("working_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("(invoice_id IS NOT NULL AND purchase_order_id IS NULL) OR (invoice_id IS NULL AND purchase_order_id IS NOT NULL)", name="ck_bill_correction_one_document"),
        sa.CheckConstraint("status IN ('draft', 'pending_approval', 'confirmed')", name="ck_bill_correction_status"),
    )
    op.create_index("ix_bill_corrections_queue", "bill_corrections", ["branch_id", "status", "updated_at"])


def downgrade():
    op.drop_index("ix_bill_corrections_queue", table_name="bill_corrections")
    op.drop_table("bill_corrections")
