"""Add invitation authentication, refresh sessions, and tenant RLS.

Revision ID: 20260804_0002
Revises: 20260803_0001
"""

from alembic import op
import sqlalchemy as sa


revision = "20260804_0002"
down_revision = "20260803_0001"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "conversations",
    "learning_profiles",
    "materials",
    "quiz_sessions",
    "answer_records",
    "mistake_records",
)


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column("role", sa.String(16), server_default="user", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("is_disabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "users", sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE users SET username = 'legacy_' || id::text WHERE username IS NULL")
    op.alter_column("users", "username", nullable=False)
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_check_constraint("ck_users_role", "users", "role IN ('admin', 'user')")

    op.create_table(
        "invite_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("max_uses > 0", name="ck_invite_codes_max_uses"),
        sa.CheckConstraint("use_count >= 0", name="ck_invite_codes_use_count"),
        sa.CheckConstraint(
            "use_count <= max_uses", name="ck_invite_codes_use_count_limit"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_invite_codes_code_hash", "invite_codes", ["code_hash"], unique=True)
    op.create_index(
        "ix_invite_codes_created_by_user_id",
        "invite_codes",
        ["created_by_user_id"],
        unique=False,
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_token_id", sa.Integer(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["replaced_by_token_id"], ["refresh_tokens.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True
    )
    op.create_index(
        "ix_refresh_tokens_session_id", "refresh_tokens", ["session_id"], unique=False
    )
    op.create_index(
        "ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False
    )
    op.create_index(
        "ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"], unique=False
    )
    op.create_index(
        "ix_refresh_tokens_user_session",
        "refresh_tokens",
        ["user_id", "session_id"],
        unique=False,
    )

    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{table}_tenant_isolation" ON "{table}" '
            "USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer) "
            "WITH CHECK (user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer)"
        )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f'DROP POLICY IF EXISTS "{table}_tenant_isolation" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

    op.drop_index("ix_refresh_tokens_user_session", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_session_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_invite_codes_created_by_user_id", table_name="invite_codes")
    op.drop_index("ix_invite_codes_code_hash", table_name="invite_codes")
    op.drop_table("invite_codes")

    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_index("ix_users_username", table_name="users")
    op.execute(
        "UPDATE users SET email = username || '@downgrade.invalid' WHERE email IS NULL"
    )
    op.alter_column("users", "email", existing_type=sa.String(255), nullable=False)
    op.drop_column("users", "disabled_at")
    op.drop_column("users", "is_disabled")
    op.drop_column("users", "role")
    op.drop_column("users", "username")
