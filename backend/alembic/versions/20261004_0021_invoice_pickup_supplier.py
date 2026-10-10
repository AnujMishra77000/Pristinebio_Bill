"""Associate new invoice pickup snapshots with the chosen supplier.

Revision ID: 20261004_0021
Revises: 20261004_0020
"""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0021"
down_revision = "20261004_0020"
branch_labels = None
depends_on = None


def upgrade():
    # Do not guess historical suppliers from address text or rewrite old bills.
    with op.batch_alter_table("invoices") as batch:
        batch.add_column(sa.Column("supplier_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_invoices_supplier", "suppliers", ["supplier_id"], ["id"])
        batch.create_index("ix_invoices_supplier_id", ["supplier_id"])


def downgrade():
    with op.batch_alter_table("invoices") as batch:
        batch.drop_index("ix_invoices_supplier_id")
        batch.drop_constraint("fk_invoices_supplier", type_="foreignkey")
        batch.drop_column("supplier_id")
