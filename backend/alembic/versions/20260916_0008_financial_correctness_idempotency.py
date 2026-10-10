"""Add persistent invoice and purchase-order creation idempotency records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260916_0008"
down_revision: str | None = "20260905_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "invoice_creation_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("invoice_id", sa.Integer(), nullable=True, unique=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.UniqueConstraint("branch_id", "idempotency_key", name="uq_invoice_creation_branch_key"),
    )
    op.create_table(
        "purchase_order_creation_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("purchase_order_id", sa.Integer(), nullable=True, unique=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
        sa.UniqueConstraint("branch_id", "idempotency_key", name="uq_purchase_order_creation_branch_key"),
    )


def downgrade() -> None:
    op.drop_table("purchase_order_creation_requests")
    op.drop_table("invoice_creation_requests")
