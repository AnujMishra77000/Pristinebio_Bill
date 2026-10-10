"""Preserve consignee PAN and contact details on invoice snapshots."""

import sqlalchemy as sa
from alembic import op


revision = "20260930_0016"
down_revision = "20260917_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("consignee_pan", sa.String(length=10)))
    op.add_column("invoices", sa.Column("consignee_email", sa.String(length=255)))
    op.add_column("invoices", sa.Column("consignee_phone", sa.String(length=30)))


def downgrade():
    op.drop_column("invoices", "consignee_phone")
    op.drop_column("invoices", "consignee_email")
    op.drop_column("invoices", "consignee_pan")
