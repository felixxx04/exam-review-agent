"""Rename character count and persist unified chunk location metadata.

Revision ID: 20260925_0009
Revises: 20260909_0008
"""

from alembic import op
import sqlalchemy as sa


revision = "20260925_0009"
down_revision = "20260909_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "material_chunks",
        "token_count",
        new_column_name="char_count",
        existing_type=sa.Integer(),
        existing_nullable=True,
    )
    op.add_column("material_chunks", sa.Column("slide_number", sa.Integer()))
    op.add_column("material_chunks", sa.Column("section_title", sa.Text()))
    op.add_column("material_chunks", sa.Column("section_level", sa.Integer()))
    op.add_column("material_chunks", sa.Column("parent_chunk_index", sa.Integer()))
    op.add_column("material_chunks", sa.Column("char_start", sa.Integer()))
    op.add_column("material_chunks", sa.Column("char_end", sa.Integer()))


def downgrade() -> None:
    op.drop_column("material_chunks", "char_end")
    op.drop_column("material_chunks", "char_start")
    op.drop_column("material_chunks", "parent_chunk_index")
    op.drop_column("material_chunks", "section_level")
    op.drop_column("material_chunks", "section_title")
    op.drop_column("material_chunks", "slide_number")
    op.alter_column(
        "material_chunks",
        "char_count",
        new_column_name="token_count",
        existing_type=sa.Integer(),
        existing_nullable=True,
    )
