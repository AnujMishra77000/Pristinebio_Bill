"""Add purchaser master and purchase-order purchaser snapshots."""

import sqlalchemy as sa
from alembic import op


revision = "20260917_0014"
down_revision = "20260916_0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "purchasers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("gstin", sa.String(length=15)),
        sa.Column("pan", sa.String(length=10)),
        sa.Column("email", sa.String(length=255)),
        sa.Column("phone", sa.String(length=30)),
        sa.Column("address_name", sa.String(length=255)),
        sa.Column("address_line1", sa.String(length=255), nullable=False),
        sa.Column("address_line2", sa.String(length=255)),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=100), nullable=False),
        sa.Column("state_code", sa.String(length=2), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_purchasers_branch_active", "purchasers", ["branch_id", "is_active", "name"])
    op.create_index("ix_purchasers_branch_gstin", "purchasers", ["branch_id", "gstin"])

    op.add_column("purchase_orders", sa.Column("purchaser_id", sa.Integer(), sa.ForeignKey("purchasers.id")))
    op.add_column("purchase_orders", sa.Column("purchaser_name", sa.String(length=255)))
    op.add_column("purchase_orders", sa.Column("purchaser_gstin", sa.String(length=15)))
    op.add_column("purchase_orders", sa.Column("purchaser_pan", sa.String(length=10)))
    op.add_column("purchase_orders", sa.Column("purchaser_email", sa.String(length=255)))
    op.add_column("purchase_orders", sa.Column("purchaser_phone", sa.String(length=30)))
    op.add_column("purchase_orders", sa.Column("purchaser_address_line1", sa.String(length=255)))
    op.add_column("purchase_orders", sa.Column("purchaser_address_line2", sa.String(length=255)))
    op.add_column("purchase_orders", sa.Column("purchaser_city", sa.String(length=100)))
    op.add_column("purchase_orders", sa.Column("purchaser_state", sa.String(length=100)))
    op.add_column("purchase_orders", sa.Column("purchaser_state_code", sa.String(length=2)))
    op.add_column("purchase_orders", sa.Column("purchaser_postal_code", sa.String(length=20)))
    op.create_index("ix_purchase_orders_purchaser", "purchase_orders", ["purchaser_id"])


def downgrade():
    raise RuntimeError("Purchaser master history is forward-only")
