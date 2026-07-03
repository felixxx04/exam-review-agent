"""add memory system tables

Revision ID: 20260703_0001
Revises: 06c68121755a
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260703_0001"
down_revision = "06c68121755a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("conversations", sa.Column("last_message_at", sa.DateTime(), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("last_memory_updated_at", sa.DateTime(), nullable=True),
    )

    op.add_column("materials", sa.Column("storage_path", sa.String(length=1000), nullable=True))
    op.add_column("materials", sa.Column("mime_type", sa.String(length=255), nullable=True))
    op.add_column("materials", sa.Column("hash", sa.String(length=128), nullable=True))
    op.add_column("materials", sa.Column("processed_at", sa.DateTime(), nullable=True))
    op.add_column("materials", sa.Column("parse_error", sa.Text(), nullable=True))
    op.create_index("ix_materials_hash", "materials", ["hash"])

    with op.batch_alter_table("answer_records") as batch_op:
        batch_op.add_column(sa.Column("quiz_session_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("feedback", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("score", sa.Float(), nullable=True))
        batch_op.create_index(
            "ix_answer_records_quiz_session_id",
            ["quiz_session_id"],
        )
        batch_op.create_foreign_key(
            "fk_answer_records_quiz_session_id_quiz_sessions",
            "quiz_sessions",
            ["quiz_session_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("USER", "ASSISTANT", "SYSTEM", name="messagerole"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("material_scope", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_conversation_messages_conversation_id",
        "conversation_messages",
        ["conversation_id"],
    )

    op.create_table(
        "learning_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("current_subject", sa.String(length=200), nullable=True),
        sa.Column("review_goal", sa.Text(), nullable=True),
        sa.Column("weak_concepts", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("frequent_questions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("active_materials", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("preferences", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_learning_profiles_user_id",
        "learning_profiles",
        ["user_id"],
        unique=True,
    )

    op.create_table(
        "material_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.String(length=100), nullable=False),
        sa.Column("text_preview", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("chunk_id"),
    )
    op.create_index("ix_material_chunks_material_id", "material_chunks", ["material_id"])
    op.create_index("ix_material_chunks_chunk_id", "material_chunks", ["chunk_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_material_chunks_chunk_id", table_name="material_chunks")
    op.drop_index("ix_material_chunks_material_id", table_name="material_chunks")
    op.drop_table("material_chunks")

    op.drop_index("ix_learning_profiles_user_id", table_name="learning_profiles")
    op.drop_table("learning_profiles")

    op.drop_index(
        "ix_conversation_messages_conversation_id",
        table_name="conversation_messages",
    )
    op.drop_table("conversation_messages")

    with op.batch_alter_table("answer_records") as batch_op:
        batch_op.drop_constraint(
            "fk_answer_records_quiz_session_id_quiz_sessions",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_answer_records_quiz_session_id")
        batch_op.drop_column("score")
        batch_op.drop_column("feedback")
        batch_op.drop_column("quiz_session_id")

    op.drop_index("ix_materials_hash", table_name="materials")
    op.drop_column("materials", "parse_error")
    op.drop_column("materials", "processed_at")
    op.drop_column("materials", "hash")
    op.drop_column("materials", "mime_type")
    op.drop_column("materials", "storage_path")

    op.drop_column("conversations", "last_memory_updated_at")
    op.drop_column("conversations", "last_message_at")
    op.drop_column("conversations", "message_count")
    op.drop_column("conversations", "summary")
