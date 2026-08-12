"""Fence stale material processing attempts after a recovered lease.

Revision ID: 20260812_0007
Revises: 20260809_0006
"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_0007"
down_revision = "20260809_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "materials",
        sa.Column("processing_lease_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("materials", "processing_lease_id")
