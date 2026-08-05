"""Add account deletion jobs and per-user upload quotas.

Revision ID: 20260805_0004
Revises: 20260805_0003
"""

from alembic import op
import sqlalchemy as sa


revision = "20260805_0004"
down_revision = "20260805_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("file_limit", sa.Integer(), server_default="100", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column(
            "storage_limit_bytes",
            sa.BigInteger(),
            server_default="2147483648",
            nullable=False,
        ),
    )
    op.create_check_constraint("ck_users_file_limit", "users", "file_limit >= 0")
    op.create_check_constraint(
        "ck_users_storage_limit_bytes", "users", "storage_limit_bytes >= 0"
    )

    op.drop_constraint(
        "invite_codes_created_by_user_id_fkey", "invite_codes", type_="foreignkey"
    )
    op.alter_column("invite_codes", "created_by_user_id", nullable=True)
    op.create_foreign_key(
        "invite_codes_created_by_user_id_fkey",
        "invite_codes",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "account_deletion_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("status_token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_account_deletion_jobs_attempt_count"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed')",
            name="ck_account_deletion_jobs_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_account_deletion_jobs_public_id",
        "account_deletion_jobs",
        ["public_id"],
        unique=True,
    )
    op.create_index(
        "ix_account_deletion_jobs_status",
        "account_deletion_jobs",
        ["status"],
    )
    op.create_index(
        "uq_account_deletion_jobs_active_user",
        "account_deletion_jobs",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        "ix_account_deletion_jobs_user_status",
        "account_deletion_jobs",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_account_deletion_jobs_user_status", table_name="account_deletion_jobs"
    )
    op.drop_index(
        "uq_account_deletion_jobs_active_user",
        table_name="account_deletion_jobs",
    )
    op.drop_index("ix_account_deletion_jobs_status", table_name="account_deletion_jobs")
    op.drop_index(
        "ix_account_deletion_jobs_public_id", table_name="account_deletion_jobs"
    )
    op.drop_table("account_deletion_jobs")

    op.execute("DELETE FROM invite_codes WHERE created_by_user_id IS NULL")
    op.drop_constraint(
        "invite_codes_created_by_user_id_fkey", "invite_codes", type_="foreignkey"
    )
    op.alter_column("invite_codes", "created_by_user_id", nullable=False)
    op.create_foreign_key(
        "invite_codes_created_by_user_id_fkey",
        "invite_codes",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("ck_users_storage_limit_bytes", "users", type_="check")
    op.drop_constraint("ck_users_file_limit", "users", type_="check")
    op.drop_column("users", "storage_limit_bytes")
    op.drop_column("users", "file_limit")
