"""Add manufacturer master, manufacturer-linked products and invoice snapshots."""

import sqlalchemy as sa
from alembic import op


revision = "20261001_0018"
down_revision = "20261001_0017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "manufacturers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("branch_id", "code", name="uq_manufacturers_branch_code"),
    )
    op.add_column("products", sa.Column("manufacturer_id", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("manufacturer_product_code", sa.String(length=100), nullable=True))
    op.create_foreign_key(
        "fk_products_manufacturer_id_manufacturers",
        "products",
        "manufacturers",
        ["manufacturer_id"],
        ["id"],
    )
    op.create_index(
        "uq_products_branch_manufacturer_code",
        "products",
        ["branch_id", "manufacturer_id", "manufacturer_product_code"],
        unique=True,
        postgresql_where=sa.text("manufacturer_id IS NOT NULL AND manufacturer_product_code IS NOT NULL"),
        sqlite_where=sa.text("manufacturer_id IS NOT NULL AND manufacturer_product_code IS NOT NULL"),
    )
    op.add_column("invoice_lines", sa.Column("manufacturer_name", sa.String(length=255), nullable=True))
    op.add_column("invoice_lines", sa.Column("manufacturer_code", sa.String(length=30), nullable=True))
    op.add_column("invoice_lines", sa.Column("manufacturer_product_code", sa.String(length=100), nullable=True))


def downgrade():
    op.drop_column("invoice_lines", "manufacturer_product_code")
    op.drop_column("invoice_lines", "manufacturer_code")
    op.drop_column("invoice_lines", "manufacturer_name")
    op.drop_index("uq_products_branch_manufacturer_code", table_name="products")
    op.drop_constraint("fk_products_manufacturer_id_manufacturers", "products", type_="foreignkey")
    op.drop_column("products", "manufacturer_product_code")
    op.drop_column("products", "manufacturer_id")
    op.drop_table("manufacturers")
