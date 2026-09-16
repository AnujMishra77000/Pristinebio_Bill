"""Add immutable invoice PDF snapshot and generation metadata.

Revision ID: 20260827_0003
Revises: 20260825_0002
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260827_0003"
down_revision: str | None = "20260825_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("logo_data_uri", sa.Text(), nullable=True))

    invoice_columns = [
        sa.Column("bank_account_id", sa.Integer(), nullable=True),
        sa.Column("irn", sa.String(length=100), nullable=True),
        sa.Column("signed_qr_data", sa.Text(), nullable=True),
        sa.Column("e_way_bill_number", sa.String(length=50), nullable=True),
        sa.Column("e_way_bill_date", sa.Date(), nullable=True),
        sa.Column("acknowledgement_number", sa.String(length=50), nullable=True),
        sa.Column("acknowledgement_date", sa.Date(), nullable=True),
        sa.Column("vehicle_type", sa.String(length=100), nullable=True),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("seller_legal_name", sa.String(length=255), nullable=True),
        sa.Column("seller_trade_name", sa.String(length=255), nullable=True),
        sa.Column("seller_logo_data_uri", sa.Text(), nullable=True),
        sa.Column("seller_pan", sa.String(length=10), nullable=True),
        sa.Column("seller_address_line1", sa.String(length=255), nullable=True),
        sa.Column("seller_address_line2", sa.String(length=255), nullable=True),
        sa.Column("seller_city", sa.String(length=100), nullable=True),
        sa.Column("seller_state", sa.String(length=100), nullable=True),
        sa.Column("seller_postal_code", sa.String(length=20), nullable=True),
        sa.Column("seller_phone", sa.String(length=30), nullable=True),
        sa.Column("seller_email", sa.String(length=255), nullable=True),
        sa.Column("bank_name", sa.String(length=255), nullable=True),
        sa.Column("bank_account_name", sa.String(length=255), nullable=True),
        sa.Column("bank_account_number", sa.String(length=50), nullable=True),
        sa.Column("bank_ifsc_code", sa.String(length=20), nullable=True),
        sa.Column("bank_branch_name", sa.String(length=255), nullable=True),
        sa.Column("transporter_name", sa.String(length=255), nullable=True),
        sa.Column("transporter_gstin", sa.String(length=15), nullable=True),
        sa.Column("terms_title", sa.String(length=255), nullable=True),
        sa.Column("terms_body", sa.Text(), nullable=True),
        sa.Column("pdf_sha256", sa.String(length=64), nullable=True),
        sa.Column("pdf_template_version", sa.String(length=50), nullable=True),
        sa.Column("pdf_storage_key", sa.String(length=500), nullable=True),
    ]
    for column in invoice_columns:
        op.add_column("invoices", column)
    op.create_foreign_key(
        "fk_invoices_bank_account_id_bank_accounts",
        "invoices",
        "bank_accounts",
        ["bank_account_id"],
        ["id"],
    )

    op.add_column(
        "invoice_lines",
        sa.Column(
            "other_charge",
            sa.Numeric(precision=14, scale=2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),
    )
    op.alter_column("invoice_lines", "other_charge", server_default=None)


def downgrade() -> None:
    op.drop_column("invoice_lines", "other_charge")
    op.drop_constraint("fk_invoices_bank_account_id_bank_accounts", "invoices", type_="foreignkey")
    for column_name in (
        "pdf_storage_key",
        "pdf_template_version",
        "pdf_sha256",
        "terms_body",
        "terms_title",
        "transporter_gstin",
        "transporter_name",
        "bank_branch_name",
        "bank_ifsc_code",
        "bank_account_number",
        "bank_account_name",
        "bank_name",
        "seller_email",
        "seller_phone",
        "seller_postal_code",
        "seller_state",
        "seller_city",
        "seller_address_line2",
        "seller_address_line1",
        "seller_pan",
        "seller_trade_name",
        "seller_logo_data_uri",
        "seller_legal_name",
        "expected_delivery_date",
        "vehicle_type",
        "acknowledgement_date",
        "acknowledgement_number",
        "e_way_bill_date",
        "e_way_bill_number",
        "signed_qr_data",
        "irn",
        "bank_account_id",
    ):
        op.drop_column("invoices", column_name)
    op.drop_column("companies", "logo_data_uri")
