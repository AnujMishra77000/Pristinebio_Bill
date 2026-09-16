"""Create Phase 1C invoice workflow tables.

Revision ID: 20260825_0002
Revises: 20260825_0001
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260825_0002"
down_revision: str | None = "20260825_0001"
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


invoice_status = sa.Enum(
    "draft",
    "pending_approval",
    "approved",
    "pdf_generated",
    name="invoice_status",
    native_enum=False,
    validate_strings=True,
    create_constraint=False,
)


def money_column(name: str) -> sa.Column[object]:
    return sa.Column(name, sa.Numeric(precision=14, scale=2), nullable=False)


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("buyer_customer_id", sa.Integer(), nullable=False),
        sa.Column("consignee_customer_id", sa.Integer(), nullable=True),
        sa.Column("transporter_id", sa.Integer(), nullable=True),
        sa.Column("terms_and_conditions_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("submitted_by_id", sa.Integer(), nullable=True),
        sa.Column("approved_by_id", sa.Integer(), nullable=True),
        sa.Column("pdf_generated_by_id", sa.Integer(), nullable=True),
        sa.Column("status", invoice_status, nullable=False),
        sa.Column("invoice_number", sa.String(length=80), nullable=True, unique=True),
        sa.Column("invoice_sequence", sa.Integer(), nullable=True),
        sa.Column("financial_year", sa.String(length=7), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("place_of_supply_state_code", sa.String(length=2), nullable=False),
        sa.Column("po_number", sa.String(length=100), nullable=True),
        sa.Column("po_date", sa.Date(), nullable=True),
        sa.Column("payment_terms", sa.String(length=255), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("transport_mode", sa.String(length=100), nullable=True),
        sa.Column("vehicle_number", sa.String(length=30), nullable=True),
        sa.Column("lr_number", sa.String(length=100), nullable=True),
        sa.Column("lr_date", sa.Date(), nullable=True),
        sa.Column("branch_name", sa.String(length=255), nullable=False),
        sa.Column("branch_gstin", sa.String(length=15), nullable=False),
        sa.Column("branch_state_code", sa.String(length=2), nullable=False),
        sa.Column("buyer_name", sa.String(length=255), nullable=False),
        sa.Column("buyer_gstin", sa.String(length=15), nullable=True),
        sa.Column("buyer_pan", sa.String(length=10), nullable=True),
        sa.Column("buyer_email", sa.String(length=255), nullable=True),
        sa.Column("buyer_phone", sa.String(length=30), nullable=True),
        sa.Column("buyer_address_line1", sa.String(length=255), nullable=False),
        sa.Column("buyer_address_line2", sa.String(length=255), nullable=True),
        sa.Column("buyer_city", sa.String(length=100), nullable=False),
        sa.Column("buyer_state", sa.String(length=100), nullable=False),
        sa.Column("buyer_state_code", sa.String(length=2), nullable=False),
        sa.Column("buyer_postal_code", sa.String(length=20), nullable=False),
        sa.Column("consignee_name", sa.String(length=255), nullable=True),
        sa.Column("consignee_gstin", sa.String(length=15), nullable=True),
        sa.Column("consignee_address_line1", sa.String(length=255), nullable=True),
        sa.Column("consignee_address_line2", sa.String(length=255), nullable=True),
        sa.Column("consignee_city", sa.String(length=100), nullable=True),
        sa.Column("consignee_state", sa.String(length=100), nullable=True),
        sa.Column("consignee_state_code", sa.String(length=2), nullable=True),
        sa.Column("consignee_postal_code", sa.String(length=20), nullable=True),
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
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pdf_generated_at", sa.DateTime(timezone=True), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.ForeignKeyConstraint(["buyer_customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["consignee_customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["transporter_id"], ["transporters.id"]),
        sa.ForeignKeyConstraint(["terms_and_conditions_id"], ["terms_and_conditions.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["pdf_generated_by_id"], ["users.id"]),
        sa.CheckConstraint(
            "status IN ('draft', 'pending_approval', 'approved', 'pdf_generated')",
            name="invoice_status_check",
        ),
    )
    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("hsn_sac", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=False),
        sa.Column("rate", sa.Numeric(precision=14, scale=4), nullable=False),
        money_column("discount_amount"),
        money_column("taxable_value"),
        sa.Column("gst_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("cess_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        money_column("cgst_amount"),
        money_column("sgst_amount"),
        money_column("igst_amount"),
        money_column("cess_amount"),
        money_column("line_total"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
    )
    op.create_table(
        "invoice_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), nullable=False),
        sa.Column("from_status", invoice_status, nullable=True),
        sa.Column("to_status", invoice_status, nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.CheckConstraint(
            "from_status IS NULL OR from_status IN ('draft', 'pending_approval', 'approved', 'pdf_generated')",
            name="invoice_audit_from_status_check",
        ),
        sa.CheckConstraint(
            "to_status IN ('draft', 'pending_approval', 'approved', 'pdf_generated')",
            name="invoice_audit_to_status_check",
        ),
    )
    op.create_table(
        "invoice_number_counters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("financial_year", sa.String(length=7), nullable=False),
        sa.Column("next_sequence", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"]),
        sa.UniqueConstraint("branch_id", "financial_year"),
    )


def downgrade() -> None:
    op.drop_table("invoice_number_counters")
    op.drop_table("invoice_audit_logs")
    op.drop_table("invoice_lines")
    op.drop_table("invoices")
