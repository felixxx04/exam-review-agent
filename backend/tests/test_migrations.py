from __future__ import annotations

from pathlib import Path
import ast

from sqlalchemy import CheckConstraint

from app.db.models import Material


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_v2_migrations_form_a_clean_chain():
    versions = sorted((BACKEND_ROOT / "alembic" / "versions").glob("*.py"))

    assert [path.name for path in versions] == [
        "20260803_0001_v2_postgres_pgvector.py",
        "20260804_0002_auth_sessions.py",
        "20260805_0003_private_courses.py",
        "20260805_0004_deletion_quotas.py",
        "20260808_0005_object_storage.py",
        "20260809_0006_material_processing_leases.py",
        "20260812_0007_material_processing_lease_fencing.py",
    ]
    initial = versions[0].read_text(encoding="utf-8")
    auth = versions[1].read_text(encoding="utf-8")
    courses = versions[2].read_text(encoding="utf-8")
    deletion = versions[3].read_text(encoding="utf-8")
    storage = versions[4].read_text(encoding="utf-8")
    leases = versions[5].read_text(encoding="utf-8")
    fencing = versions[6].read_text(encoding="utf-8")
    assert "down_revision = None" in initial
    assert 'down_revision = "20260803_0001"' in auth
    assert 'down_revision = "20260804_0002"' in courses
    assert 'down_revision = "20260805_0003"' in deletion
    assert 'down_revision = "20260805_0004"' in storage
    assert 'down_revision = "20260808_0005"' in leases
    assert 'down_revision = "20260809_0006"' in fencing


def test_v2_migration_enables_pgvector_and_retrieval_indexes():
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "20260803_0001_v2_postgres_pgvector.py"
    ).read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS vector" in source
    assert "Vector(dim=1024)" in source
    assert "ix_material_chunks_embedding_hnsw" in source
    assert "ix_material_chunks_lexical_search" in source


def test_production_code_has_no_in_memory_dict_store():
    app_root = BACKEND_ROOT / "app"

    assert not (app_root / "core" / "store.py").exists()
    for source_file in app_root.rglob("*.py"):
        assert "app.core.store" not in source_file.read_text(encoding="utf-8")


def test_auth_migration_adds_sessions_invites_and_tenant_rls():
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "20260804_0002_auth_sessions.py"
    ).read_text(encoding="utf-8")

    assert "invite_codes" in source
    assert "refresh_tokens" in source
    assert "username" in source
    assert "is_disabled" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "current_setting('app.current_user_id', true)" in source


def test_course_migration_adds_private_course_domain_and_ownership():
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "20260805_0003_private_courses.py"
    ).read_text(encoding="utf-8")

    for table in ("courses", "exams", "study_availabilities", "concept_masteries"):
        assert table in source
    for table in (
        "conversations",
        "learning_profiles",
        "materials",
        "quiz_sessions",
        "answer_records",
        "mistake_records",
        "concepts",
    ):
        assert f'"{table}"' in source
        assert "course_id" in source
    assert "available_minutes_override" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source


def test_course_migration_refuses_legacy_graph_loss_and_safely_collapses_downgrade():
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "20260805_0003_private_courses.py"
    ).read_text(encoding="utf-8")
    module = ast.parse(source)
    functions = {
        node.name: node for node in module.body if isinstance(node, ast.FunctionDef)
    }
    upgrade = ast.get_source_segment(source, functions["upgrade"]) or ""
    downgrade = ast.get_source_segment(source, functions["downgrade"]) or ""

    assert "_assert_legacy_concepts_empty()" in upgrade
    assert "DELETE FROM concept_dependencies" not in upgrade
    assert "DELETE FROM concepts" not in upgrade
    assert "_collapse_learning_profiles_for_legacy_schema()" in downgrade
    assert "_delete_private_concepts_for_legacy_schema()" in downgrade


def test_deletion_migration_adds_quotas_and_queryable_account_jobs():
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "20260805_0004_deletion_quotas.py"
    ).read_text(encoding="utf-8")

    assert "file_limit" in source
    assert "storage_limit_bytes" in source
    assert "account_deletion_jobs" in source
    assert "status_token_hash" in source
    assert "uq_account_deletion_jobs_active_user" in source
    assert "ON DELETE SET NULL" in source or 'ondelete="SET NULL"' in source


def test_object_storage_migration_adds_private_object_metadata_and_indexes():
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "20260808_0005_object_storage.py"
    ).read_text(encoding="utf-8")

    for column in (
        "storage_backend",
        "storage_status",
        "object_id",
        "object_key",
        "object_version_id",
        "object_etag",
    ):
        assert column in source
    assert "ix_materials_user_course_hash_storage" in source
    assert "sa.Enum(" in source
    assert 'name="ck_materials_storage_status"' in source
    assert "length=16" in source
    for status in ("reserved", "available", "deleting", "deleted"):
        assert f'"{status}"' in source
    assert "sa.String(length=16)" not in source


def test_object_storage_migration_backfill_temporarily_relaxes_forced_rls():
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "20260808_0005_object_storage.py"
    ).read_text(encoding="utf-8")

    no_force = source.index("ALTER TABLE materials NO FORCE ROW LEVEL SECURITY")
    backfill = source.index("UPDATE materials")
    force = source.index("ALTER TABLE materials FORCE ROW LEVEL SECURITY")
    assert no_force < backfill < force


def test_object_storage_migration_downgrade_checks_s3_objects_outside_forced_rls():
    source = (
        BACKEND_ROOT / "alembic" / "versions" / "20260808_0005_object_storage.py"
    ).read_text(encoding="utf-8")
    module = ast.parse(source)
    functions = {
        node.name: node for node in module.body if isinstance(node, ast.FunctionDef)
    }
    downgrade = ast.get_source_segment(source, functions["downgrade"]) or ""

    assert "ALTER TABLE materials NO FORCE ROW LEVEL SECURITY" in downgrade
    assert "storage_backend = 's3' AND object_key IS NOT NULL" in downgrade
    assert "ALTER TABLE materials FORCE ROW LEVEL SECURITY" in downgrade
    no_force = downgrade.index("ALTER TABLE materials NO FORCE ROW LEVEL SECURITY")
    s3_guard = downgrade.index("storage_backend = 's3' AND object_key IS NOT NULL")
    force = downgrade.index("ALTER TABLE materials FORCE ROW LEVEL SECURITY")
    first_drop = downgrade.index("op.drop_index")
    assert no_force < s3_guard < force < first_drop


def test_material_storage_backend_check_is_part_of_orm_metadata():
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in Material.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_materials_storage_backend" in constraints
    assert "storage_backend" in constraints["ck_materials_storage_backend"]


def test_material_storage_status_type_length_matches_existing_migration_schema():
    storage_status_type = Material.__table__.c.storage_status.type

    assert storage_status_type.length == 16


def test_material_processing_lease_migration_tracks_uncertain_writes_and_leases():
    source = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "20260809_0006_material_processing_leases.py"
    ).read_text(encoding="utf-8")

    assert "object_write_uncertain" in source
    assert "processing_lease_expires_at" in source
    assert "ix_materials_storage_processing_lease" in source


def test_material_processing_lease_fencing_migration_tracks_attempt_generation():
    source = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "20260812_0007_material_processing_lease_fencing.py"
    ).read_text(encoding="utf-8")

    assert "processing_lease_id" in source
    assert "materials" in source


def test_material_processing_lease_generation_is_part_of_orm_metadata():
    assert Material.__table__.c.processing_lease_id.nullable is True
