"""Add PostgreSQL-backed material processing jobs.

Revision ID: 20260909_0008
Revises: 20260812_0007
"""

from alembic import op
import sqlalchemy as sa


revision = "20260909_0008"
down_revision = "20260812_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "material_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("current_step", sa.String(length=64), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redis_job_id", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_material_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0",
            name="ck_material_jobs_attempts",
        ),
        sa.CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_material_jobs_progress",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            ondelete="CASCADE",
            name="fk_material_jobs_course_owner",
        ),
        sa.ForeignKeyConstraint(
            ["material_id", "user_id", "course_id"],
            ["materials.id", "materials.user_id", "materials.course_id"],
            ondelete="CASCADE",
            name="fk_material_jobs_material_scope",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_material_jobs_public_id", "material_jobs", ["public_id"], unique=True
    )
    op.create_index(
        "ix_material_jobs_idempotency_key",
        "material_jobs",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_material_jobs_user_status", "material_jobs", ["user_id", "status"]
    )
    op.create_index(
        "ix_material_jobs_queue_scan",
        "material_jobs",
        ["status", "available_at", "priority", "created_at"],
    )
    op.create_index(
        "ix_material_jobs_user_material",
        "material_jobs",
        ["user_id", "material_id"],
    )
    op.execute('ALTER TABLE "material_jobs" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "material_jobs" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY "material_jobs_tenant_isolation" ON "material_jobs" '
        "USING (user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer) "
        "WITH CHECK (user_id = NULLIF(current_setting('app.current_user_id', true), '')::integer)"
    )


def downgrade() -> None:
    op.execute(
        'DROP POLICY IF EXISTS "material_jobs_tenant_isolation" ON "material_jobs"'
    )
    op.execute('ALTER TABLE "material_jobs" DISABLE ROW LEVEL SECURITY')
    op.drop_index("ix_material_jobs_user_material", table_name="material_jobs")
    op.drop_index("ix_material_jobs_queue_scan", table_name="material_jobs")
    op.drop_index("ix_material_jobs_user_status", table_name="material_jobs")
    op.drop_index("ix_material_jobs_idempotency_key", table_name="material_jobs")
    op.drop_index("ix_material_jobs_public_id", table_name="material_jobs")
    op.drop_table("material_jobs")
