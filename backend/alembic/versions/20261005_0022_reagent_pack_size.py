"""Preserve staff-entered reagent pack sizes on transaction lines.

Revision ID: 20261005_0022
Revises: 20261004_0021
"""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0022"
down_revision = "20261004_0021"
branch_labels = None
depends_on = None


def upgrade():
    # Historical lines remain null; issued documents and PDFs are not rewritten.
    op.add_column("invoice_lines", sa.Column("pack_size", sa.String(100), nullable=True))
    op.add_column("purchase_order_lines", sa.Column("pack_size", sa.String(100), nullable=True))


def downgrade():
    op.drop_column("purchase_order_lines", "pack_size")
    op.drop_column("invoice_lines", "pack_size")
