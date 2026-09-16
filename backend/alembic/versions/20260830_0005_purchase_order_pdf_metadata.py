"""Add PDF metadata to purchase orders.

Revision ID: 20260830_0005
Revises: 20260830_0004
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260830_0005"
down_revision: str | None = "20260830_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("purchase_orders", sa.Column("pdf_sha256", sa.String(length=64), nullable=True))
    op.add_column("purchase_orders", sa.Column("pdf_template_version", sa.String(length=50), nullable=True))
    op.add_column("purchase_orders", sa.Column("pdf_storage_key", sa.String(length=255), nullable=True))
    op.add_column("purchase_orders", sa.Column("pdf_generated_by_id", sa.Integer(), nullable=True))
    op.add_column("purchase_orders", sa.Column("pdf_generated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_purchase_orders_pdf_generated_by_id_users",
        "purchase_orders",
        "users",
        ["pdf_generated_by_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_purchase_orders_pdf_generated_by_id_users", "purchase_orders", type_="foreignkey")
    op.drop_column("purchase_orders", "pdf_generated_at")
    op.drop_column("purchase_orders", "pdf_generated_by_id")
    op.drop_column("purchase_orders", "pdf_storage_key")
    op.drop_column("purchase_orders", "pdf_template_version")
    op.drop_column("purchase_orders", "pdf_sha256")
