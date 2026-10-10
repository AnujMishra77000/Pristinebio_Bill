"""Indexes for bounded registers, approvals and authorized activity queries."""

from alembic import op


revision = "20260916_0011"
down_revision = "20260916_0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_invoices_branch_status_submitted", "invoices", ["branch_id", "status", "submitted_at"])
    op.create_index("ix_invoices_branch_invoice_date", "invoices", ["branch_id", "invoice_date", "id"])
    op.create_index("ix_invoice_audits_invoice_created", "invoice_audit_logs", ["invoice_id", "created_at"])
    op.create_index("ix_pos_branch_status_submitted", "purchase_orders", ["branch_id", "status", "submitted_at"])
    op.create_index("ix_pos_branch_order_date", "purchase_orders", ["branch_id", "order_date", "id"])
    op.create_index("ix_po_audits_order_created", "purchase_order_audit_logs", ["purchase_order_id", "created_at"])
    op.create_index("ix_customers_branch_active_name", "customers", ["branch_id", "is_active", "name"])
    op.create_index("ix_products_branch_active_name", "products", ["branch_id", "is_active", "name"])
    op.create_index("ix_suppliers_branch_active_name", "suppliers", ["branch_id", "is_active", "name"])


def downgrade():
    raise RuntimeError("Operational indexes are forward-only; remove only through a reviewed migration")
