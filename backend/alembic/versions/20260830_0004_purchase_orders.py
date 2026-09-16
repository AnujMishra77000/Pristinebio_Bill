"""Add supplier and purchase-order billing tables.

Revision ID: 20260830_0004
Revises: 20260827_0003
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260830_0004"
down_revision: str | None = "20260827_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def money_column(name: str) -> sa.Column[object]:
    return sa.Column(name, sa.Numeric(precision=14, scale=2), nullable=False)


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("gstin", sa.String(length=15), nullable=True),
        sa.Column("pan", sa.String(length=10), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("address_name", sa.String(length=255), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=False),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=100), nullable=False),
        sa.Column("state_code", sa.String(length=2), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
    )
    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("purchase_order_number", sa.String(length=100), nullable=False, unique=True),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("payment_terms", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("branch_name", sa.String(length=255), nullable=False),
        sa.Column("branch_gstin", sa.String(length=15), nullable=False),
        sa.Column("branch_state_code", sa.String(length=2), nullable=False),
        sa.Column("supplier_name", sa.String(length=255), nullable=False),
        sa.Column("supplier_gstin", sa.String(length=15), nullable=True),
        sa.Column("supplier_pan", sa.String(length=10), nullable=True),
        sa.Column("supplier_email", sa.String(length=255), nullable=True),
        sa.Column("supplier_phone", sa.String(length=30), nullable=True),
        sa.Column("supplier_address_line1", sa.String(length=255), nullable=False),
        sa.Column("supplier_address_line2", sa.String(length=255), nullable=True),
        sa.Column("supplier_city", sa.String(length=100), nullable=False),
        sa.Column("supplier_state", sa.String(length=100), nullable=False),
        sa.Column("supplier_state_code", sa.String(length=2), nullable=False),
        sa.Column("supplier_postal_code", sa.String(length=20), nullable=False),
        money_column("freight_charges"),
        money_column("packing_charges"),
        money_column("other_charges"),
        money_column("discount_amount"),
        money_column("taxable_value"),
        money_column("cgst_amount"),
        money_column("sgst_amount"),
        money_column("igst_amount"),
        money_column("cess_amount"),
        money_column("unrounded_total"),
        money_column("round_off"),
        money_column("final_total"),
        sa.Column("amount_in_words", sa.String(length=500), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
    )
    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purchase_order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("hsn_sac", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("rate", sa.Numeric(precision=14, scale=4), nullable=False),
        money_column("other_charge"),
        money_column("discount_amount"),
        money_column("taxable_value"),
        sa.Column("gst_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("cess_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        money_column("cgst_amount"),
        money_column("sgst_amount"),
        money_column("igst_amount"),
        money_column("cess_amount"),
        money_column("line_total"),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
    )


def downgrade() -> None:
    op.drop_table("purchase_order_lines")
    op.drop_table("purchase_orders")
    op.drop_table("suppliers")
