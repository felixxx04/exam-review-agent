"""Track uncertain object writes and durable material processing leases.

Revision ID: 20260809_0006
Revises: 20260808_0005
"""

from alembic import op
import sqlalchemy as sa


revision = "20260809_0006"
down_revision = "20260808_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "materials",
        sa.Column(
            "object_write_uncertain",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "materials",
        sa.Column("processing_lease_expires_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_materials_storage_processing_lease",
        "materials",
        ["storage_status", "processing_status", "processing_lease_expires_at"],
    )
    op.alter_column("materials", "object_write_uncertain", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_materials_storage_processing_lease", table_name="materials")
    op.drop_column("materials", "processing_lease_expires_at")
    op.drop_column("materials", "object_write_uncertain")
