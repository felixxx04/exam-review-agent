from __future__ import annotations

from pathlib import Path
import ast


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_v2_migrations_form_a_clean_chain():
    versions = sorted((BACKEND_ROOT / "alembic" / "versions").glob("*.py"))

    assert [path.name for path in versions] == [
        "20260803_0001_v2_postgres_pgvector.py",
        "20260804_0002_auth_sessions.py",
        "20260805_0003_private_courses.py",
    ]
    initial = versions[0].read_text(encoding="utf-8")
    auth = versions[1].read_text(encoding="utf-8")
    courses = versions[2].read_text(encoding="utf-8")
    assert "down_revision = None" in initial
    assert 'down_revision = "20260803_0001"' in auth
    assert 'down_revision = "20260804_0002"' in courses


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
