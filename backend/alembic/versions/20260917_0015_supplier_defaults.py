"""Add supplier default selection and enforce one active default per branch."""

import sqlalchemy as sa
from alembic import op


revision = "20260917_0015"
down_revision = "20260917_0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "suppliers",
        sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute(
        sa.text(
            """
            WITH first_active AS (
                SELECT id,
                       ROW_NUMBER() OVER (PARTITION BY branch_id ORDER BY id) AS row_number
                FROM suppliers
                WHERE is_active = TRUE
            )
            UPDATE suppliers
            SET is_default = TRUE
            WHERE id IN (SELECT id FROM first_active WHERE row_number = 1)
            """
        )
    )
    op.alter_column("suppliers", "is_default", server_default=None)
    op.create_index(
        "uq_suppliers_branch_default",
        "suppliers",
        ["branch_id"],
        unique=True,
        postgresql_where=sa.text("is_default = true"),
    )


def downgrade():
    op.drop_index("uq_suppliers_branch_default", table_name="suppliers")
    op.drop_column("suppliers", "is_default")
