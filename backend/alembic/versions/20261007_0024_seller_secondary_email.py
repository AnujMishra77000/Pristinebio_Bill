"""Add optional seller second email and immutable transaction email snapshots.

Revision ID: 20261007_0024
Revises: 20261006_0023
"""
from alembic import op
import sqlalchemy as sa

revision = "20261007_0024"
down_revision = "20261006_0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("branches", sa.Column("secondary_email", sa.String(255), nullable=True))
    for table in ("invoices", "purchase_orders"):
        # Null identifies a legacy document. Do not infer historical emails.
        op.add_column(table, sa.Column("seller_email_addresses", sa.JSON(), nullable=True))


def downgrade():
    for table in ("purchase_orders", "invoices"):
        op.drop_column(table, "seller_email_addresses")
    op.drop_column("branches", "secondary_email")
