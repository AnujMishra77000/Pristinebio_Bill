"""Retain creation-key tombstones after explicit permanent bill deletion.

Revision ID: 20261006_0023
Revises: 20261005_0022
"""
from alembic import op
import sqlalchemy as sa

revision = "20261006_0023"
down_revision = "20261005_0022"
branch_labels = None
depends_on = None


def upgrade():
    # Existing documents, issued numbers and PDFs remain unchanged.
    for table in ("invoice_creation_requests", "purchase_order_creation_requests"):
        op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_security_audit_entity_action", "security_audit_logs", ["entity_type", "entity_id", "action"])


def downgrade():
    op.drop_index("ix_security_audit_entity_action", table_name="security_audit_logs")
    for table in ("purchase_order_creation_requests", "invoice_creation_requests"):
        op.drop_column(table, "deleted_at")
