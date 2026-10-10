"""Add Reagent Bill type and reagent-specific invoice line fields."""

import sqlalchemy as sa
from alembic import op


revision = "20261001_0017"
down_revision = "20260930_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "invoices",
        sa.Column("document_type", sa.String(length=20), server_default="sales", nullable=False),
    )
    op.add_column("invoice_lines", sa.Column("part_no", sa.String(length=100), nullable=True))
    op.add_column(
        "invoice_lines",
        sa.Column("discount_percent", sa.Numeric(precision=5, scale=2), server_default="0.00", nullable=False),
    )


def downgrade():
    op.drop_column("invoice_lines", "discount_percent")
    op.drop_column("invoice_lines", "part_no")
    op.drop_column("invoices", "document_type")
