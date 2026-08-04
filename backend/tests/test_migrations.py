from __future__ import annotations

from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_v2_migrations_form_a_clean_chain():
    versions = sorted((BACKEND_ROOT / "alembic" / "versions").glob("*.py"))

    assert [path.name for path in versions] == [
        "20260803_0001_v2_postgres_pgvector.py",
        "20260804_0002_auth_sessions.py",
    ]
    initial = versions[0].read_text(encoding="utf-8")
    auth = versions[1].read_text(encoding="utf-8")
    assert "down_revision = None" in initial
    assert 'down_revision = "20260803_0001"' in auth


def test_v2_migration_enables_pgvector_and_retrieval_indexes():
    source = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "20260803_0001_v2_postgres_pgvector.py"
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
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "20260804_0002_auth_sessions.py"
    ).read_text(encoding="utf-8")

    assert "invite_codes" in source
    assert "refresh_tokens" in source
    assert "username" in source
    assert "is_disabled" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "current_setting('app.current_user_id', true)" in source
