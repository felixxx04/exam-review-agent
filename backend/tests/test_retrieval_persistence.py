"""Task 3.1 RED contracts for PostgreSQL-backed hybrid retrieval.

These tests deliberately exercise the public retrieval boundary instead of
Chroma internals.  ``InMemoryRetrievalSession`` is a restart-safe test double
for the persistence adapter; a real PostgreSQL/pgvector run belongs to the
integration suite once Docker is available.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pytest

from app.services.retrieval_service import RetrievalService

try:  # Keep collection useful while the RED API is not implemented yet.
    from app.services.retrieval_service import Evidence, RetrievalResponse
except ImportError:  # pragma: no cover - expected during the RED phase
    Evidence = None
    RetrievalResponse = None


VECTOR_DIMENSION = 1024


@dataclass
class _PersistedChunk:
    user_id: int
    course_id: int
    material_id: int
    chunk_id: str
    text: str
    metadata: dict[str, Any]
    embedding: list[float]
    embedding_model: str


class InMemoryRetrievalSession:
    """Small persistence adapter double shared by multiple service instances.

    It intentionally exposes adapter-shaped methods, rather than Chroma's
    collection API, so a service restart cannot accidentally fall back to
    process-local BM25 state.
    """

    def __init__(self) -> None:
        self.rows: dict[str, _PersistedChunk] = {}

    async def upsert_chunks(
        self,
        *,
        user_id: int,
        course_id: int,
        material_id: int,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
        embedding_model: str,
    ) -> list[str]:
        ids: list[str] = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            chunk_id = str(chunk["chunk_id"])
            ids.append(chunk_id)
            metadata = dict(chunk.get("metadata") or {})
            self.rows[chunk_id] = _PersistedChunk(
                user_id=user_id,
                course_id=course_id,
                material_id=material_id,
                chunk_id=chunk_id,
                text=str(chunk["text"]),
                metadata=metadata,
                embedding=list(embedding),
                embedding_model=embedding_model,
            )
        return ids

    async def delete_chunks(
        self, *, user_id: int, course_id: int, chunk_ids: list[str]
    ) -> None:
        for chunk_id in chunk_ids:
            row = self.rows.get(chunk_id)
            if row and row.user_id == user_id and row.course_id == course_id:
                del self.rows[chunk_id]

    def count(self, *, user_id: int | None = None, course_id: int | None = None) -> int:
        rows = self.rows.values()
        if user_id is not None:
            rows = (row for row in rows if row.user_id == user_id)
        if course_id is not None:
            rows = (row for row in rows if row.course_id == course_id)
        return sum(1 for _ in rows)


class _FixedEmbeddingService:
    model_name = "test-embedding"

    def __init__(
        self,
        *,
        dimension: int = VECTOR_DIMENSION,
        non_finite: float | None = None,
    ) -> None:
        self.dimension = dimension
        self.non_finite = non_finite

    def _vector(self, _text: str) -> list[float]:
        vector = [0.0] * self.dimension
        vector[0] = 1.0
        if self.non_finite is not None:
            vector[-1] = self.non_finite
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class _FixedReranker:
    def __init__(self, score: float = 0.9) -> None:
        self.score = score

    def predict(self, pairs: list[tuple[str, str]], **_: Any) -> list[float]:
        return [self.score for _ in pairs]


def _chunk(chunk_id: str, text: str, source: str, *, page: int = 1) -> dict[str, Any]:
    return {
        "chunk_id": chunk_id,
        "text": text,
        "metadata": {
            "source": source,
            "page_number": page,
            "slide_number": None,
            "section_title": "持久化检索",
            "char_start": 10,
            "char_end": 10 + len(text),
        },
    }


def _service(
    session: InMemoryRetrievalSession,
    *,
    embedding: _FixedEmbeddingService | None = None,
    reranker: _FixedReranker | None = None,
    quality_threshold: float = 0.3,
) -> RetrievalService:
    return RetrievalService(
        db_session=session,
        embedding_service=embedding or _FixedEmbeddingService(),
        reranker=reranker or _FixedReranker(),
        quality_threshold=quality_threshold,
    )


@pytest.mark.asyncio
async def test_search_returns_structured_response_and_stable_evidence() -> None:
    session = InMemoryRetrievalSession()
    service = _service(session)

    await service.index_chunks(
        user_id=11,
        course_id=101,
        material_id=9001,
        chunks=[_chunk("stable-1", "数据库事务保证原子性", "database.pdf", page=3)],
    )

    response = await service.search(
        user_id=11,
        course_id=101,
        query="事务原子性",
        top_k=1,
        material_scope=["database.pdf"],
    )

    assert RetrievalResponse is not None
    assert Evidence is not None
    assert isinstance(response, RetrievalResponse)
    assert response.status == "ok"
    assert len(response.evidences) == 1
    evidence = response.evidences[0]
    assert isinstance(evidence, Evidence)
    assert evidence.chunk_id == "stable-1"
    assert evidence.text == "数据库事务保证原子性"
    assert evidence.user_id == 11
    assert evidence.course_id == 101
    assert evidence.material_id == 9001
    assert evidence.source == "database.pdf"
    assert evidence.page_number == 3
    assert evidence.char_start == 10
    assert evidence.char_end == 20


@pytest.mark.asyncio
async def test_status_distinguishes_partial_and_no_results() -> None:
    session = InMemoryRetrievalSession()
    service = _service(session)
    await service.index_chunks(
        user_id=11,
        course_id=101,
        material_id=9001,
        chunks=[_chunk("one", "事务内容", "database.pdf")],
    )

    partial = await service.search(user_id=11, course_id=101, query="事务", top_k=3)
    assert partial.status == "partial"
    assert len(partial.evidences) == 1

    empty = await service.search(user_id=11, course_id=999, query="事务", top_k=3)
    assert empty.status == "no_results"
    assert empty.evidences == []


@pytest.mark.asyncio
async def test_low_reranker_scores_report_quality_gate_failure() -> None:
    session = InMemoryRetrievalSession()
    service = _service(
        session,
        reranker=_FixedReranker(score=0.05),
        quality_threshold=0.3,
    )
    await service.index_chunks(
        user_id=11,
        course_id=101,
        material_id=9001,
        chunks=[_chunk("low-score", "无关内容", "database.pdf")],
    )

    response = await service.search(user_id=11, course_id=101, query="事务", top_k=3)
    assert response.status == "quality_gate_failed"
    assert response.evidences == []


@pytest.mark.asyncio
async def test_persistence_survives_service_restart_and_delete() -> None:
    session = InMemoryRetrievalSession()
    first = _service(session)
    await first.index_chunks(
        user_id=11,
        course_id=101,
        material_id=9001,
        chunks=[_chunk("durable-1", "可恢复的事务内容", "database.pdf")],
    )
    assert session.count(user_id=11, course_id=101) == 1

    restarted = _service(session)
    recovered = await restarted.search(user_id=11, course_id=101, query="事务", top_k=1)
    assert recovered.status == "ok"
    assert recovered.evidences[0].chunk_id == "durable-1"

    await restarted.delete_chunks(user_id=11, course_id=101, chunk_ids=["durable-1"])
    after_delete = await _service(session).search(
        user_id=11, course_id=101, query="事务", top_k=1
    )
    assert after_delete.status == "no_results"
    assert after_delete.evidences == []


@pytest.mark.asyncio
async def test_search_enforces_user_course_and_material_scope() -> None:
    session = InMemoryRetrievalSession()
    service = _service(session)
    await service.index_chunks(
        user_id=11,
        course_id=101,
        material_id=9001,
        chunks=[_chunk("owner-course", "共享关键词 课程一", "course-one.pdf")],
    )
    await service.index_chunks(
        user_id=11,
        course_id=202,
        material_id=9002,
        chunks=[_chunk("other-course", "共享关键词 课程二", "course-two.pdf")],
    )
    await service.index_chunks(
        user_id=22,
        course_id=101,
        material_id=9003,
        chunks=[_chunk("other-user", "共享关键词 其他用户", "other-user.pdf")],
    )

    owner = await service.search(
        user_id=11,
        course_id=101,
        query="共享关键词",
        top_k=5,
        material_scope=["course-one.pdf"],
    )
    assert {item.chunk_id for item in owner.evidences} == {"owner-course"}
    assert all(item.user_id == 11 and item.course_id == 101 for item in owner.evidences)

    other_course = await service.search(
        user_id=11,
        course_id=202,
        query="共享关键词",
        top_k=5,
    )
    assert {item.chunk_id for item in other_course.evidences} == {"other-course"}

    other_user = await service.search(
        user_id=22,
        course_id=101,
        query="共享关键词",
        top_k=5,
    )
    assert {item.chunk_id for item in other_user.evidences} == {"other-user"}


@pytest.mark.asyncio
async def test_embedding_dimension_is_rejected_before_persistence() -> None:
    session = InMemoryRetrievalSession()
    service = _service(session, embedding=_FixedEmbeddingService(dimension=2))

    with pytest.raises(ValueError, match="1024|dimension"):
        await service.index_chunks(
            user_id=11,
            course_id=101,
            material_id=9001,
            chunks=[_chunk("bad-dimension", "事务内容", "database.pdf")],
        )
    assert session.rows == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("non_finite", [math.nan, math.inf, -math.inf])
async def test_non_finite_embedding_is_rejected_by_persistence_adapter(
    non_finite: float,
) -> None:
    session = InMemoryRetrievalSession()
    service = _service(
        session,
        embedding=_FixedEmbeddingService(non_finite=non_finite),
    )

    with pytest.raises(ValueError, match="finite|finite"):
        await service.index_chunks(
            user_id=11,
            course_id=101,
            material_id=9001,
            chunks=[_chunk("non-finite", "事务内容", "database.pdf")],
        )
    assert session.rows == {}


@pytest.mark.asyncio
async def test_reindexing_stable_chunk_id_is_idempotent() -> None:
    session = InMemoryRetrievalSession()
    service = _service(session)
    await service.index_chunks(
        user_id=11,
        course_id=101,
        material_id=9001,
        chunks=[_chunk("stable-retry", "第一次内容", "database.pdf")],
    )
    await service.index_chunks(
        user_id=11,
        course_id=101,
        material_id=9001,
        chunks=[_chunk("stable-retry", "恢复后的内容", "database.pdf")],
    )

    assert session.count(user_id=11, course_id=101) == 1
    response = await _service(session).search(
        user_id=11, course_id=101, query="恢复", top_k=1
    )
    assert response.evidences[0].text == "恢复后的内容"
