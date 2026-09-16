"""Add seller-profile bank and terms defaults."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260905_0007"
down_revision: str | None = "20260831_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("branches", sa.Column("bank_name", sa.String(length=255), nullable=True))
    op.add_column("branches", sa.Column("bank_branch_name", sa.String(length=255), nullable=True))
    op.add_column("branches", sa.Column("bank_account_name", sa.String(length=255), nullable=True))
    op.add_column("branches", sa.Column("bank_account_number", sa.String(length=50), nullable=True))
    op.add_column("branches", sa.Column("bank_ifsc_code", sa.String(length=20), nullable=True))
    op.add_column("branches", sa.Column("terms_body", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("branches", "terms_body")
    op.drop_column("branches", "bank_ifsc_code")
    op.drop_column("branches", "bank_account_number")
    op.drop_column("branches", "bank_account_name")
    op.drop_column("branches", "bank_branch_name")
    op.drop_column("branches", "bank_name")
