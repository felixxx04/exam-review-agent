"""Add private S3-compatible object storage metadata for materials.

Revision ID: 20260808_0005
Revises: 20260805_0004
"""

from alembic import op
import sqlalchemy as sa


revision = "20260808_0005"
down_revision = "20260805_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "materials",
        sa.Column(
            "storage_backend",
            sa.String(length=32),
            server_default="legacy_local",
            nullable=False,
        ),
    )
    op.add_column(
        "materials",
        sa.Column(
            "storage_status",
            sa.Enum(
                "reserved",
                "available",
                "deleting",
                "deleted",
                name="ck_materials_storage_status",
                native_enum=False,
                create_constraint=True,
                length=16,
            ),
            server_default="available",
            nullable=False,
        ),
    )
    op.add_column("materials", sa.Column("object_id", sa.String(length=64)))
    op.add_column("materials", sa.Column("object_key", sa.String(length=1000)))
    op.add_column("materials", sa.Column("object_version_id", sa.String(length=512)))
    op.add_column("materials", sa.Column("object_etag", sa.String(length=512)))
    op.execute("ALTER TABLE materials NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "UPDATE materials "
        "SET object_id = md5('material-object-' || id::text) "
        "WHERE object_id IS NULL"
    )
    op.alter_column("materials", "object_id", nullable=False)
    op.execute("ALTER TABLE materials FORCE ROW LEVEL SECURITY")
    op.create_check_constraint(
        "ck_materials_storage_backend",
        "materials",
        "storage_backend IN ('legacy_local', 's3')",
    )
    op.create_index("ix_materials_object_id", "materials", ["object_id"], unique=True)
    op.create_index(
        "ix_materials_user_course_hash_storage",
        "materials",
        ["user_id", "course_id", "hash", "storage_status"],
    )
    op.alter_column("materials", "storage_backend", server_default=None)
    op.alter_column("materials", "storage_status", server_default=None)


def downgrade() -> None:
    # Alembic runs without a tenant GUC. The app role owns this table, so FORCE
    # RLS would otherwise hide live S3 metadata from the destructive guard.
    op.execute("ALTER TABLE materials NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM materials
                WHERE storage_backend = 's3' AND object_key IS NOT NULL
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade while S3 material objects are still tracked';
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE materials FORCE ROW LEVEL SECURITY")
    op.drop_index("ix_materials_user_course_hash_storage", table_name="materials")
    op.drop_index("ix_materials_object_id", table_name="materials")
    op.drop_constraint("ck_materials_storage_status", "materials", type_="check")
    op.drop_constraint("ck_materials_storage_backend", "materials", type_="check")
    op.drop_column("materials", "object_etag")
    op.drop_column("materials", "object_version_id")
    op.drop_column("materials", "object_key")
    op.drop_column("materials", "object_id")
    op.drop_column("materials", "storage_status")
    op.drop_column("materials", "storage_backend")
