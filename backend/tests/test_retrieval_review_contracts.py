from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

import app.services.retrieval_service as retrieval_module
from app.services.retrieval_service import RetrievalService

_lexical_tokens = getattr(retrieval_module, "_lexical_tokens", lambda text: text)


class _Embedding:
    model_name = "review-test"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


class _FixedReranker:
    def predict(self, pairs: list[tuple[str, str]], **_: Any) -> list[float]:
        return [0.9 for _ in pairs]


class _VectorStore:
    def __init__(self) -> None:
        self.add_scopes: list[str] = []
        self.search_scopes: list[str] = []
        self.deleted_scopes: list[str] = []
        self.metadata_deletes: list[tuple[str, dict[str, Any]]] = []
        self.search_results: dict[str, list[dict[str, Any]]] = {}

    def add(self, user_id: str, *args: Any, **kwargs: Any) -> list[str]:
        self.add_scopes.append(user_id)
        return list(kwargs.get("ids") or [])

    def search(self, user_id: str, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.search_scopes.append(user_id)
        return self.search_results.get(user_id, [])

    def delete_collection(self, user_id: str) -> None:
        self.deleted_scopes.append(user_id)

    def delete_by_metadata(self, user_id: str, metadata_filter: dict[str, Any]) -> None:
        self.metadata_deletes.append((user_id, metadata_filter))


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return self._rows


class _DatabaseSession:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.flush_count = 0

    async def execute(self, _statement: Any) -> _Result:
        return _Result(self.rows)

    async def flush(self) -> None:
        self.flush_count += 1


class _AdapterSession:
    def __init__(self) -> None:
        self.rows = {
            "chunk-1": SimpleNamespace(
                user_id=11,
                course_id=22,
                material_id=33,
                chunk_id="chunk-1",
                content="adapter text",
                chunk_metadata={"source": "adapter.pdf"},
                embedding=[0.0] * 1024,
            )
        }

    async def upsert_chunks(self, **_: Any) -> None:
        return None


class _HybridSession:
    def __init__(self, responses: list[list[Any]]) -> None:
        self.responses = responses
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        rows = self.responses[len(self.statements) - 1]

        class Result:
            def all(self) -> list[Any]:
                return rows

        return Result()


def test_constructor_keeps_legacy_positional_contract_and_rrf_k() -> None:
    vector_store = object()
    embedding = object()
    service = RetrievalService(0.7, 17, vector_store, embedding)

    assert service.quality_threshold == 0.7
    assert service._rrf_k == 17
    assert service._vector_store is vector_store
    assert service._embedding_service is embedding

    db = object()
    interim = RetrievalService(db, embedding, object(), vector_store, 0.7)
    assert interim._db_session is db
    assert interim._embedding_service is embedding
    assert interim.quality_threshold == 0.7


def test_lexical_tokenizer_separates_chinese_characters_for_index_and_query() -> None:
    assert _lexical_tokens("数据库事务 ACID") == "数 据 库 事 务 acid"


def test_cross_encoder_is_lazy_process_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _CrossEncoder:
        def __init__(self, name: str) -> None:
            calls.append(name)

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(CrossEncoder=_CrossEncoder),
    )
    monkeypatch.setattr(RetrievalService, "_cross_encoder", None, raising=False)

    first = RetrievalService()
    second = RetrievalService()
    assert first._get_reranker() is second._get_reranker()
    assert calls == ["BAAI/bge-reranker-base"]


@pytest.mark.asyncio
async def test_database_reindex_refreshes_search_and_location_fields() -> None:
    row = SimpleNamespace(
        chunk_id="chunk-1",
        user_id=1,
        course_id=2,
        material_id=3,
        content="old",
        text_preview="old",
        embedding=None,
        embedding_model=None,
        chunk_metadata={},
        lexical_tokens="old",
        content_hash="old",
        page_number=99,
        slide_number=99,
        section_title="old",
        section_level=99,
        char_start=99,
        char_end=99,
        char_count=99,
    )
    session = _DatabaseSession([row])
    service = RetrievalService(db_session=session)
    metadata = {
        "source": "new.pdf",
        "page_number": 4,
        "slide_number": 5,
        "section_title": "重建",
        "section_level": 2,
        "char_start": 10,
        "char_end": 16,
        "char_count": 6,
    }

    await service._upsert_database(
        user_id=1,
        course_id=2,
        material_id=3,
        chunks=[{"chunk_id": "chunk-1", "text": "数据库事务", "metadata": metadata}],
        embeddings=[[0.0] * 1024],
        embedding_model="review-test",
    )

    assert row.lexical_tokens == _lexical_tokens("数据库事务")
    assert row.content_hash
    assert row.page_number == 4
    assert row.slide_number == 5
    assert row.section_title == "重建"
    assert row.section_level == 2
    assert row.char_start == 10
    assert row.char_end == 16
    assert row.char_count == 6


@pytest.mark.asyncio
async def test_database_reindex_missing_intent_is_atomic() -> None:
    existing = SimpleNamespace(
        chunk_id="present",
        user_id=1,
        course_id=2,
        material_id=3,
        content="old",
        text_preview="old",
        embedding=None,
        embedding_model=None,
        chunk_metadata={},
    )
    session = _DatabaseSession([existing])
    service = RetrievalService(db_session=session)

    with pytest.raises(ValueError, match="intent not found"):
        await service._upsert_database(
            user_id=1,
            course_id=2,
            material_id=3,
            chunks=[
                {"chunk_id": "present", "text": "new", "metadata": {}},
                {"chunk_id": "missing", "text": "should not apply", "metadata": {}},
            ],
            embeddings=[[0.0] * 1024, [0.0] * 1024],
            embedding_model="review-test",
        )

    assert existing.content == "old"
    assert session.flush_count == 0


@pytest.mark.asyncio
async def test_legacy_course_scope_is_consistent_for_index_search_and_delete() -> None:
    store = _VectorStore()
    service = RetrievalService(
        vector_store=store,
        embedding_service=_Embedding(),
    )

    await service.index_chunks(
        "user-1",
        [{"chunk_id": "chunk-1", "text": "text", "metadata": {}}],
        course_id=22,
    )
    await service.search("user-1", "text", course_id=22)
    await service.delete_collection("user-1", course_id=22)

    assert store.add_scopes == ["user-1_course_22"]
    # The first lookup must use the unified course scope.  A second lookup
    # may read the legacy user-level collection during migration.
    assert store.search_scopes[0] == "user-1_course_22"
    assert store.deleted_scopes == ["user-1_course_22"]


@pytest.mark.asyncio
async def test_legacy_user_scope_is_read_and_course_delete_is_selective() -> None:
    store = _VectorStore()
    store.search_results["user-1"] = [
        {
            "id": "legacy-1",
            "document": "legacy course text",
            "metadata": {"course_id": 22, "source": "legacy.pdf"},
            "embedding": [1.0, 0.0],
        }
    ]
    service = RetrievalService(
        vector_store=store,
        embedding_service=_Embedding(),
        reranker=_FixedReranker(),
    )

    response = await service.search("user-1", "legacy", course_id=22)
    assert response.evidences[0].chunk_id == "legacy-1"
    await service.delete_collection("user-1", course_id=22)
    assert store.metadata_deletes == [("user-1", {"course_id": 22})]


@pytest.mark.asyncio
async def test_legacy_results_are_merged_when_new_course_scope_has_results() -> None:
    store = _VectorStore()
    store.search_results["user-1_course_22"] = [
        {
            "id": "new-1",
            "document": "new course text",
            "metadata": {"course_id": 22, "source": "new.pdf"},
            "embedding": [1.0, 0.0],
        }
    ]
    store.search_results["user-1"] = [
        {
            "id": "legacy-1",
            "document": "legacy course text",
            "metadata": {"course_id": 22, "source": "legacy.pdf"},
            "embedding": [1.0, 0.0],
        }
    ]
    service = RetrievalService(
        vector_store=store,
        embedding_service=_Embedding(),
        reranker=_FixedReranker(),
    )

    response = await service.search("user-1", "text", top_k=2, course_id=22)

    assert {evidence.chunk_id for evidence in response.evidences} == {
        "new-1",
        "legacy-1",
    }


@pytest.mark.asyncio
async def test_database_user_id_is_normalized_and_invalid_values_rejected() -> None:
    service = RetrievalService(db_session=object(), embedding_service=_Embedding())
    with pytest.raises(ValueError, match="user_id"):
        await service.search("subject-user", "query", course_id=22)
    with pytest.raises(ValueError, match="user_id"):
        RetrievalService._database_user_id(1.9)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_adapter_normalizes_string_user_id_for_search_and_delete() -> None:
    session = _AdapterSession()
    service = RetrievalService(
        db_session=session,
        embedding_service=type(
            "Embedding",
            (),
            {"embed_query": lambda self, _: [0.0] * 1024},
        )(),
        reranker=_FixedReranker(),
    )

    response = await service.search("11", "adapter", course_id=22)
    assert response.evidences[0].chunk_id == "chunk-1"
    await service.delete_collection("11", course_id=22)
    assert session.rows == {}


@pytest.mark.asyncio
async def test_database_hybrid_candidates_use_rrf_and_push_scope_before_limit() -> None:
    dense_row = SimpleNamespace(
        chunk_id="dense", chunk_metadata={"source": "allowed.pdf"}
    )
    lexical_row = SimpleNamespace(
        chunk_id="lexical", chunk_metadata={"source": "allowed.pdf"}
    )
    session = _HybridSession(responses=[[(dense_row, 0.1)], [(lexical_row, 0.9)]])
    service = RetrievalService(db_session=session, rrf_k=60)

    candidates = await service._database_hybrid_candidates(
        user_id=1,
        course_id=22,
        query="数据库",
        query_embedding=[0.0] * 1024,
        top_k=2,
        material_scope=["allowed.pdf"],
        metadata_filter={"source": {"$in": ["allowed.pdf"]}},
    )

    assert [row.chunk_id for row, _ in candidates] == ["dense", "lexical"]
    assert candidates[0][1] == pytest.approx(1 / 61)
    for statement in session.statements:
        sql = str(statement)
        assert sql.index("original_filename") < sql.index("LIMIT")
