from __future__ import annotations

import hashlib
import os
import sys
import uuid

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import bind_tenant_context
from app.db.models import (
    Course,
    FileType,
    Material,
    MaterialChunk,
    ProcessingStatus,
    StorageStatus,
    User,
)
from app.services.retrieval_service import RetrievalService


POSTGRES_INTEGRATION_URL = os.getenv("POSTGRES_INTEGRATION_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_INTEGRATION_URL,
    reason="POSTGRES_INTEGRATION_URL is required for pgvector retrieval tests",
)


def _async_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql+psycopg://")
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql+psycopg2://")
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")
    return url


class DeterministicEmbedding:
    """Stable 1024-dimensional vectors without model downloads or network calls."""

    model_name = "integration/deterministic-1024"

    @staticmethod
    def _vector(text: str) -> list[float]:
        vector = [0.0] * 1024
        for token in str(text).lower().split():
            index = int(hashlib.sha256(token.encode()).hexdigest()[:8], 16) % 1024
            vector[index] += 1.0
        return vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        if text == "lexicalneedle":
            return self._vector("densequery")
        return self._vector(text)


class DeterministicReranker:
    def predict(self, pairs: list[tuple[str, str]], **_kwargs: object) -> list[float]:
        return [1.0 if "anchor" in text else 0.8 for _query, text in pairs]


def _material(*, user_id: int, course_id: int, filename: str, suffix: str) -> Material:
    return Material(
        user_id=user_id,
        course_id=course_id,
        filename=filename,
        original_filename=filename,
        file_type=FileType.PDF,
        file_size=1,
        page_count=1,
        processing_status=ProcessingStatus.READY,
        storage_backend="legacy_local",
        storage_status=StorageStatus.AVAILABLE,
        object_key=f"integration/{suffix}/{filename}",
        mime_type="application/pdf",
    )


@pytest.mark.asyncio
async def test_postgres_pgvector_retrieval_persists_hybrid_scope_and_deletes():
    """Exercise the durable retrieval path against PostgreSQL and pgvector."""
    assert POSTGRES_INTEGRATION_URL is not None
    engine = create_async_engine(
        _async_url(POSTGRES_INTEGRATION_URL), pool_pre_ping=True
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:12]
    user_id: int | None = None
    embedding = DeterministicEmbedding()
    reranker = DeterministicReranker()

    try:
        async with session_factory() as session:
            user = User(
                username=f"retrieval_{suffix}",
                email=None,
                hashed_password="integration-test-hash",
                display_name="Retrieval Integration",
            )
            session.add(user)
            await session.commit()
            user_id = user.id

        assert user_id is not None
        async with session_factory() as session:
            await bind_tenant_context(session, user_id)
            course_one = Course(user_id=user_id, name=f"Retrieval A {suffix}")
            course_two = Course(user_id=user_id, name=f"Retrieval B {suffix}")
            session.add_all([course_one, course_two])
            await session.flush()
            material_one = _material(
                user_id=user_id,
                course_id=course_one.id,
                filename=f"alpha-{suffix}.pdf",
                suffix=suffix,
            )
            material_two = _material(
                user_id=user_id,
                course_id=course_one.id,
                filename=f"beta-{suffix}.pdf",
                suffix=suffix,
            )
            material_three = _material(
                user_id=user_id,
                course_id=course_two.id,
                filename=f"gamma-{suffix}.pdf",
                suffix=suffix,
            )
            session.add_all([material_one, material_two, material_three])
            await session.flush()
            rows = [
                MaterialChunk(
                    material_id=material_one.id,
                    user_id=user_id,
                    course_id=course_one.id,
                    chunk_id=f"{suffix}-alpha-dense",
                    content="",
                    content_hash="",
                    lexical_tokens="",
                    chunk_metadata={
                        "source": material_one.original_filename,
                        "topic": "target",
                        "published": True,
                        "priority": 2,
                        "kind": "dense",
                    },
                ),
                MaterialChunk(
                    material_id=material_one.id,
                    user_id=user_id,
                    course_id=course_one.id,
                    chunk_id=f"{suffix}-alpha-lexical",
                    content="",
                    content_hash="",
                    lexical_tokens="",
                    chunk_metadata={
                        "source": material_one.original_filename,
                        "topic": "other",
                        "kind": "lexical",
                    },
                ),
                MaterialChunk(
                    material_id=material_two.id,
                    user_id=user_id,
                    course_id=course_one.id,
                    chunk_id=f"{suffix}-beta-target",
                    content="",
                    content_hash="",
                    lexical_tokens="",
                    chunk_metadata={
                        "source": material_two.original_filename,
                        "topic": "target",
                        "kind": "other-material",
                    },
                ),
                MaterialChunk(
                    material_id=material_three.id,
                    user_id=user_id,
                    course_id=course_two.id,
                    chunk_id=f"{suffix}-gamma-other-course",
                    content="",
                    content_hash="",
                    lexical_tokens="",
                    chunk_metadata={
                        "source": material_three.original_filename,
                        "topic": "target",
                        "kind": "other-course",
                    },
                ),
                MaterialChunk(
                    material_id=material_one.id,
                    user_id=user_id,
                    course_id=course_one.id,
                    chunk_id=f"{suffix}-alpha-string-priority",
                    content="",
                    content_hash="",
                    lexical_tokens="",
                    chunk_metadata={
                        "source": material_one.original_filename,
                        "topic": "target",
                        "published": True,
                        "priority": "2",
                        "kind": "wrong-json-type",
                    },
                ),
            ]
            session.add_all(rows)
            await session.commit()

            service = RetrievalService(
                db_session=session,
                embedding_service=embedding,
                reranker=reranker,
                quality_threshold=0.0,
            )
            await service.index_chunks(
                user_id,
                [
                    {
                        "text": "densequery anchor algebra target",
                        "metadata": rows[0].chunk_metadata,
                    },
                    {
                        "text": "lexicalneedle 词条 retrieval",
                        "metadata": rows[1].chunk_metadata,
                    },
                ],
                course_id=course_one.id,
                material_id=material_one.id,
                chunk_ids=[rows[0].chunk_id, rows[1].chunk_id],
            )
            await service.index_chunks(
                user_id,
                [
                    {
                        "text": "densequery",
                        "metadata": rows[2].chunk_metadata,
                    }
                ],
                course_id=course_one.id,
                material_id=material_two.id,
                chunk_ids=[rows[2].chunk_id],
            )
            await service.index_chunks(
                user_id,
                [
                    {
                        "text": "anchor target in another course",
                        "metadata": rows[3].chunk_metadata,
                    }
                ],
                course_id=course_two.id,
                material_id=material_three.id,
                chunk_ids=[rows[3].chunk_id],
            )
            await service.index_chunks(
                user_id,
                [{"text": "anchor", "metadata": rows[4].chunk_metadata}],
                course_id=course_one.id,
                material_id=material_one.id,
                chunk_ids=[rows[4].chunk_id],
            )
            await session.commit()
            persisted_embedding = await session.scalar(
                select(MaterialChunk.embedding).where(
                    MaterialChunk.chunk_id == rows[0].chunk_id
                )
            )
            assert persisted_embedding is not None
            assert len(persisted_embedding) == 1024
            lexical_tokens = await session.scalar(
                select(MaterialChunk.lexical_tokens).where(
                    MaterialChunk.chunk_id == rows[1].chunk_id
                )
            )
            assert "lexicalneedle" in lexical_tokens
            lexical_match = await session.scalar(
                select(MaterialChunk.chunk_id).where(
                    MaterialChunk.chunk_id == rows[1].chunk_id,
                    func.to_tsvector("simple", MaterialChunk.lexical_tokens).op("@@")(
                        func.plainto_tsquery("simple", "lexicalneedle")
                    ),
                )
            )
            assert lexical_match == rows[1].chunk_id

            response = await service.search(
                user_id,
                "anchor retrieval",
                top_k=10,
                course_id=course_one.id,
                apply_quality_gate=False,
            )
            result_ids = {item.chunk_id for item in response}
            assert response.status == "partial"
            assert {rows[0].chunk_id, rows[1].chunk_id}.issubset(result_ids)
            assert rows[3].chunk_id not in result_ids

            dense_only = await service.search(
                user_id,
                "algebra",
                top_k=1,
                course_id=course_one.id,
                apply_quality_gate=False,
            )
            assert [item.chunk_id for item in dense_only] == [rows[0].chunk_id]

            lexical_candidates = await service._database_hybrid_candidates(
                user_id=user_id,
                course_id=course_one.id,
                query="lexicalneedle",
                query_embedding=embedding.embed_query("lexicalneedle"),
                # The query embedding intentionally points at the dense row,
                # while the token exists only in the lexical row.  Keep two
                # final slots so both independent leg winners remain visible
                # after RRF truncation.
                top_k=2,
                material_scope=None,
                metadata_filter=None,
            )
            fused = {row.chunk_id: score for row, score in lexical_candidates}
            assert set(fused) == {rows[1].chunk_id, rows[2].chunk_id}
            assert fused[rows[2].chunk_id] == pytest.approx(1 / (service._rrf_k + 1))
            assert fused[rows[1].chunk_id] == pytest.approx(1 / (service._rrf_k + 1))

            filtered = await service.search(
                user_id,
                "anchor",
                top_k=1,
                course_id=course_one.id,
                material_scope=[material_one.original_filename],
                metadata_filter={"topic": "target", "published": True, "priority": 2},
                apply_quality_gate=False,
            )
            assert [item.chunk_id for item in filtered] == [rows[0].chunk_id]
            assert filtered[0].metadata["source"] == material_one.original_filename

            string_priority = await service.search(
                user_id,
                "anchor",
                top_k=1,
                course_id=course_one.id,
                metadata_filter={"priority": "2"},
                apply_quality_gate=False,
            )
            assert [item.chunk_id for item in string_priority] == [rows[4].chunk_id]

            other_course = await service.search(
                user_id,
                "anchor",
                top_k=10,
                course_id=course_two.id,
                apply_quality_gate=False,
            )
            assert [item.chunk_id for item in other_course] == [rows[3].chunk_id]

        # A fresh session and service instance represent a worker restart.
        async with session_factory() as restarted_session:
            await bind_tenant_context(restarted_session, user_id)
            restarted = RetrievalService(
                db_session=restarted_session,
                embedding_service=embedding,
                reranker=reranker,
                quality_threshold=0.0,
            )
            after_restart = await restarted.search(
                user_id,
                "anchor retrieval",
                top_k=10,
                course_id=course_one.id,
                apply_quality_gate=False,
            )
            assert {item.chunk_id for item in after_restart} >= {
                rows[0].chunk_id,
                rows[1].chunk_id,
            }

            await restarted.delete_chunks(
                user_id, [rows[1].chunk_id], course_id=course_one.id
            )
            await restarted_session.commit()
            deleted_chunk = await restarted_session.scalar(
                select(MaterialChunk.id).where(
                    MaterialChunk.chunk_id == rows[1].chunk_id
                )
            )
            assert deleted_chunk is None

            await restarted.delete_collection(user_id, course_id=course_one.id)
            await restarted_session.commit()
            course_one_count = await restarted_session.scalar(
                select(func.count(MaterialChunk.id)).where(
                    MaterialChunk.user_id == user_id,
                    MaterialChunk.course_id == course_one.id,
                )
            )
            other_course_count = await restarted_session.scalar(
                select(func.count(MaterialChunk.id)).where(
                    MaterialChunk.user_id == user_id,
                    MaterialChunk.course_id == course_two.id,
                )
            )
            assert course_one_count == 0
            assert other_course_count == 1
    finally:
        primary_exception = sys.exc_info()[1]
        cleanup_error: BaseException | None = None
        if user_id is not None:
            try:
                async with session_factory() as cleanup_session:
                    await bind_tenant_context(cleanup_session, user_id)
                    await cleanup_session.execute(
                        delete(MaterialChunk).where(MaterialChunk.user_id == user_id)
                    )
                    await cleanup_session.execute(
                        delete(Material).where(Material.user_id == user_id)
                    )
                    await cleanup_session.execute(
                        delete(Course).where(Course.user_id == user_id)
                    )
                    await cleanup_session.execute(
                        delete(User).where(User.id == user_id)
                    )
                    await cleanup_session.commit()
            except BaseException as exc:  # pragma: no cover - only cleanup failures
                cleanup_error = exc
        try:
            await engine.dispose()
        except BaseException as exc:  # pragma: no cover - only cleanup failures
            cleanup_error = cleanup_error or exc
        if cleanup_error is not None:
            if primary_exception is None:
                raise cleanup_error
            primary_exception.add_note(
                "PostgreSQL retrieval integration cleanup also failed "
                f"({type(cleanup_error).__name__})"
            )
