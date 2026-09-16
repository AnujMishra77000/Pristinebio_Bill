"""Add delivery note date to sales invoices.

Revision ID: 20260831_0006
Revises: 20260830_0005
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260831_0006"
down_revision: str | None = "20260830_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("delivery_note_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "delivery_note_date")
