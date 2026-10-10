"""Separate company headers from pickup addresses on new transactions.

Revision ID: 20261004_0020
Revises: 20261003_0019
"""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0020"
down_revision = "20261003_0019"
branch_labels = None
depends_on = None


def upgrade():
    # No backfill: historical documents retain their original address mapping
    # and stored PDF references. A non-null company snapshot identifies new bills.
    for table in ("invoices", "purchase_orders"):
        op.add_column(table, sa.Column("company_registered_address", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("pickup_address", sa.Text(), nullable=True))


def downgrade():
    for table in ("purchase_orders", "invoices"):
        op.drop_column(table, "pickup_address")
        op.drop_column(table, "company_registered_address")
