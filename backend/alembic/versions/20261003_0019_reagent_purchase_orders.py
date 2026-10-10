"""Add reagent purchase orders without changing existing domestic orders.

Revision ID: 20261003_0019
Revises: 20261001_0018
"""
from alembic import op
import sqlalchemy as sa

revision = "20261003_0019"
down_revision = "20261001_0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("purchase_orders", sa.Column("document_type", sa.String(20), server_default="domestic_oils", nullable=False))
    for name, type_ in (
        ("place_of_supply_state_code", sa.String(2)), ("delivery_note_date", sa.Date()),
        ("po_reference_number", sa.String(100)), ("po_reference_date", sa.Date()),
        ("transport_mode", sa.String(100)), ("vehicle_number", sa.String(30)),
        ("vehicle_type", sa.String(100)), ("lr_number", sa.String(100)),
        ("lr_date", sa.Date()), ("consignee_details", sa.JSON()),
    ):
        op.add_column("purchase_orders", sa.Column(name, type_, nullable=True))
    op.create_check_constraint("ck_purchase_order_document_type", "purchase_orders", "document_type IN ('domestic_oils', 'reagent')")
    op.create_index("ix_purchase_orders_branch_type_date", "purchase_orders", ["branch_id", "document_type", "order_date", "id"])
    for name, type_ in (
        ("manufacturer_id", sa.Integer()), ("manufacturer_name", sa.String(255)),
        ("manufacturer_code", sa.String(30)), ("manufacturer_product_code", sa.String(100)),
        ("part_no", sa.String(100)),
    ):
        op.add_column("purchase_order_lines", sa.Column(name, type_, nullable=True))
    op.add_column("purchase_order_lines", sa.Column("discount_percent", sa.Numeric(5, 2), server_default="0", nullable=False))
    op.create_foreign_key("fk_po_line_manufacturer", "purchase_order_lines", "manufacturers", ["manufacturer_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_po_line_manufacturer", "purchase_order_lines", type_="foreignkey")
    for name in ("discount_percent", "part_no", "manufacturer_product_code", "manufacturer_code", "manufacturer_name", "manufacturer_id"):
        op.drop_column("purchase_order_lines", name)
    op.drop_index("ix_purchase_orders_branch_type_date", table_name="purchase_orders")
    op.drop_constraint("ck_purchase_order_document_type", "purchase_orders", type_="check")
    for name in ("consignee_details", "lr_date", "lr_number", "vehicle_type", "vehicle_number", "transport_mode", "po_reference_date", "po_reference_number", "delivery_note_date", "place_of_supply_state_code", "document_type"):
        op.drop_column("purchase_orders", name)
