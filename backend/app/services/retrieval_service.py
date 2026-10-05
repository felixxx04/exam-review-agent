"""Hybrid retrieval service.

The database adapter is the durable path used by the current application.  A
small Chroma-compatible path is retained for callers and tests that have not
yet been migrated to dependency-injected database sessions.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Sequence

try:
    from sqlalchemy import func, select
except Exception:  # pragma: no cover - optional during lightweight tests
    func = None
    select = None

try:
    from app.db.models import Material, MaterialChunk
except Exception:  # pragma: no cover - import remains optional for unit tests
    Material = None
    MaterialChunk = None

try:
    from app.db.vector_store import VectorStore
except Exception:  # pragma: no cover - construction is intentionally lazy
    VectorStore = None


VECTOR_DIMENSION = 1024


@dataclass
class SearchResult:
    """A backward-compatible retrieval result."""

    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Evidence(SearchResult):
    """A result with stable identity and source-location information."""

    chunk_id: str = ""
    user_id: int | str | None = None
    course_id: int | str | None = None
    material_id: int | str | None = None
    source: str | None = None
    page_number: int | None = None
    slide_number: int | None = None
    section_title: str | None = None
    section_level: int | None = None
    char_start: int | None = None
    char_end: int | None = None


@dataclass
class RetrievalResponse(Sequence[Evidence]):
    """Structured response which deliberately remains list-like for callers."""

    status: str
    evidences: list[Evidence] = field(default_factory=list)

    def __iter__(self) -> Iterator[Evidence]:
        return iter(self.evidences)

    def __len__(self) -> int:
        return len(self.evidences)

    def __getitem__(self, index: int | slice) -> Evidence | list[Evidence]:
        return self.evidences[index]

    def __bool__(self) -> bool:
        return bool(self.evidences)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, RetrievalResponse):
            return self.status == other.status and self.evidences == other.evidences
        if isinstance(other, (list, tuple)):
            return self.evidences == list(other)
        return NotImplemented


class RetrievalService:
    """Dense/lexical hybrid retrieval with durable and legacy adapters."""

    def __init__(
        self,
        db_session: Any | None = None,
        embedding_service: Any | None = None,
        reranker: Any | None = None,
        vector_store: Any | None = None,
        quality_threshold: float = 0.3,
        **_: Any,
    ) -> None:
        self._db_session = db_session
        self._embedding_service = embedding_service
        self._reranker = reranker
        self._vector_store = vector_store
        self.quality_threshold = quality_threshold
        # Retained as a compatibility observation point for legacy cleanup
        # tests. It is never consulted by the durable PostgreSQL path.
        self._bm25_indices: dict[str, bool] = {}

    @property
    def _uses_adapter(self) -> bool:
        return self._db_session is not None and hasattr(
            self._db_session, "upsert_chunks"
        )

    @property
    def _uses_database(self) -> bool:
        return self._db_session is not None and not self._uses_adapter

    @property
    def _vector_store(self) -> Any | None:
        return self.__dict__.get("__vector_store")

    @_vector_store.setter
    def _vector_store(self, value: Any | None) -> None:
        self.__dict__["__vector_store"] = value

    def _get_embedding_service(self) -> Any:
        if self._embedding_service is None:
            from app.services.embedding_service import EmbeddingService

            self._embedding_service = EmbeddingService()
        return self._embedding_service

    @classmethod
    def _get_cross_encoder(cls) -> Any:
        from sentence_transformers import CrossEncoder

        return CrossEncoder("BAAI/bge-reranker-base")

    def _get_reranker(self) -> Any:
        if self._reranker is None:
            self._reranker = self._get_cross_encoder()
        return self._reranker

    def _get_vector_store(self) -> Any:
        if self._vector_store is None:
            store_type = VectorStore
            if store_type is None:
                from app.db.vector_store import VectorStore as store_type
            self._vector_store = store_type()
        return self._vector_store

    @staticmethod
    def _scope_key(user_id: str, course_id: int | str | None) -> str:
        return user_id if course_id is None else f"{user_id}_course_{course_id}"

    @staticmethod
    def _embedding_model(service: Any) -> str:
        return str(
            getattr(service, "model_name", None)
            or getattr(service, "_model_name", None)
            or getattr(service, "model", None)
            or "unknown"
        )

    @staticmethod
    def _validate_embeddings(embeddings: Iterable[Sequence[float]], *, durable: bool) -> None:
        for vector in embeddings:
            if durable and len(vector) != VECTOR_DIMENSION:
                raise ValueError(
                    f"embedding dimension must be {VECTOR_DIMENSION}, got {len(vector)}"
                )
            if any(not math.isfinite(float(value)) for value in vector):
                raise ValueError("embedding values must be finite")

    @staticmethod
    def _chunk_payload(chunk: dict[str, Any], chunk_id: str) -> dict[str, Any]:
        metadata = dict(chunk.get("metadata") or {})
        return {
            "chunk_id": chunk_id,
            "text": str(chunk.get("text", chunk.get("content", ""))),
            "metadata": metadata,
        }

    async def index_chunks(
        self,
        user_id: int | str,
        chunks: list[dict[str, Any]],
        course_id: int | str | None = None,
        chunk_ids: list[str] | None = None,
        material_id: int | str | None = None,
    ) -> list[str]:
        """Embed and persist chunks, updating stable IDs when supplied."""
        if chunk_ids is None:
            chunk_ids = [
                str(item.get("chunk_id") or uuid.uuid4()) for item in chunks
            ]
        if len(chunk_ids) != len(chunks) or len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("chunk_ids must be unique and match the indexed chunks")
        if self._uses_adapter or self._uses_database:
            if course_id is None:
                raise ValueError("course_id is required for database retrieval")
            if material_id is None:
                material_id = chunks[0].get("material_id") if chunks else None
            if material_id is None:
                raise ValueError("material_id is required for database retrieval")

        payloads = [self._chunk_payload(item, cid) for item, cid in zip(chunks, chunk_ids, strict=True)]
        texts = [item["text"] for item in payloads]
        embedding_service = self._get_embedding_service()
        embeddings = list(embedding_service.embed_documents(texts))
        if len(embeddings) != len(payloads):
            raise ValueError("embedding service returned an unexpected number of vectors")
        self._validate_embeddings(embeddings, durable=self._uses_adapter or self._uses_database)

        if self._uses_adapter:
            await self._db_session.upsert_chunks(
                user_id=user_id,
                course_id=course_id,
                material_id=material_id,
                chunks=payloads,
                embeddings=embeddings,
                embedding_model=self._embedding_model(embedding_service),
            )
            return list(chunk_ids)
        if self._uses_database:
            await self._upsert_database(
                user_id=user_id,
                course_id=course_id,
                material_id=material_id,
                chunks=payloads,
                embeddings=embeddings,
                embedding_model=self._embedding_model(embedding_service),
            )
            return list(chunk_ids)

        metadatas = []
        for item in payloads:
            metadata = dict(item["metadata"])
            metadata.setdefault("chunk_id", item["chunk_id"])
            if course_id is not None:
                metadata.setdefault("course_id", course_id)
            if material_id is not None:
                metadata.setdefault("material_id", material_id)
            metadatas.append(metadata)
        self._get_vector_store().add(
            str(user_id), embeddings, texts, metadatas, ids=list(chunk_ids)
        )
        self._bm25_indices[self._scope_key(str(user_id), course_id)] = True
        return list(chunk_ids)

    async def _upsert_database(
        self,
        *,
        user_id: int | str,
        course_id: int | str,
        material_id: int | str,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
        embedding_model: str,
    ) -> None:
        if MaterialChunk is None or select is None:
            raise RuntimeError("SQLAlchemy MaterialChunk model is unavailable")
        ids = [item["chunk_id"] for item in chunks]
        result = await self._db_session.execute(
            select(MaterialChunk).where(
                MaterialChunk.chunk_id.in_(ids),
                MaterialChunk.user_id == user_id,
                MaterialChunk.course_id == course_id,
                MaterialChunk.material_id == material_id,
            )
        )
        existing = {str(row.chunk_id): row for row in result.scalars().all()}
        for item, vector in zip(chunks, embeddings, strict=True):
            row = existing.get(item["chunk_id"])
            if row is None:
                # Production indexing pre-allocates intent rows.  Refuse to
                # silently create a second source of truth here.
                raise ValueError(f"material chunk intent not found: {item['chunk_id']}")
            row.user_id = user_id
            row.course_id = course_id
            row.material_id = material_id
            row.content = item["text"]
            row.text_preview = item["text"][:500]
            row.embedding = vector
            row.embedding_model = embedding_model
            row.chunk_metadata = item["metadata"]
        await self._db_session.flush()

    async def delete_chunks(
        self,
        user_id: int | str,
        chunk_ids: list[str],
        course_id: int | str | None = None,
    ) -> None:
        if self._uses_adapter:
            if course_id is None:
                raise ValueError("course_id is required for database retrieval")
            await self._db_session.delete_chunks(
                user_id=user_id, course_id=course_id, chunk_ids=chunk_ids
            )
            return
        if self._uses_database:
            if MaterialChunk is None or select is None:
                raise RuntimeError("SQLAlchemy MaterialChunk model is unavailable")
            statement = select(MaterialChunk).where(
                MaterialChunk.chunk_id.in_(chunk_ids), MaterialChunk.user_id == user_id
            )
            if course_id is not None:
                statement = statement.where(MaterialChunk.course_id == course_id)
            result = await self._db_session.execute(statement)
            for row in result.scalars().all():
                await self._db_session.delete(row)
            await self._db_session.flush()
            return
        self._get_vector_store().delete(str(user_id), chunk_ids)
        scope_key = self._scope_key(str(user_id), course_id)
        store = self._get_vector_store()
        remaining = None
        if hasattr(store, "count"):
            remaining = store.count(str(user_id))
        elif hasattr(store, "documents"):
            remaining = sum(
                1
                for item in store.documents
                if item.get("user_id") == str(user_id)
                and (course_id is None or item.get("metadata", {}).get("course_id") == course_id)
            )
        if remaining == 0:
            self._bm25_indices.pop(scope_key, None)

    async def delete_collection(
        self, user_id: int | str, *, course_id: int | str | None = None
    ) -> None:
        if self._uses_adapter:
            if hasattr(self._db_session, "delete_collection"):
                await self._db_session.delete_collection(
                    user_id=user_id, course_id=course_id
                )
            else:
                rows = getattr(self._db_session, "rows", {})
                for chunk_id, row in list(rows.items()):
                    if getattr(row, "user_id", None) != user_id:
                        continue
                    if course_id is not None and getattr(row, "course_id", None) != course_id:
                        continue
                    del rows[chunk_id]
        elif self._uses_database:
            if MaterialChunk is None or select is None:
                return
            statement = select(MaterialChunk).where(MaterialChunk.user_id == user_id)
            if course_id is not None:
                statement = statement.where(MaterialChunk.course_id == course_id)
            result = await self._db_session.execute(statement)
            for row in result.scalars().all():
                await self._db_session.delete(row)
            await self._db_session.flush()
        else:
            scope = str(user_id)
            if course_id is not None:
                scope = f"{scope}_course_{course_id}"
            self._get_vector_store().delete_collection(scope)
            self._bm25_indices.pop(scope, None)

    @staticmethod
    def _row_values(row: Any) -> tuple[str, str, dict[str, Any], Any, Any, Any]:
        if isinstance(row, dict):
            chunk_id = str(row.get("chunk_id") or row.get("id") or "")
            text = str(row.get("text") or row.get("content") or row.get("document") or "")
            metadata = dict(row.get("metadata") or row.get("chunk_metadata") or {})
            return chunk_id, text, metadata, row.get("embedding"), row.get("distance"), row
        chunk_id = str(getattr(row, "chunk_id", getattr(row, "id", "")))
        text = str(getattr(row, "content", getattr(row, "text", "")))
        metadata = dict(getattr(row, "chunk_metadata", getattr(row, "metadata", {})) or {})
        return chunk_id, text, metadata, getattr(row, "embedding", None), getattr(row, "distance", None), row

    async def _adapter_rows(self) -> list[Any]:
        rows = getattr(self._db_session, "rows", {})
        values = rows.values() if isinstance(rows, dict) else rows
        return list(values)

    async def _database_rows(self, user_id: int | str, course_id: int | str) -> list[Any]:
        if MaterialChunk is None or select is None:
            return []
        result = await self._db_session.execute(
            select(MaterialChunk).where(
                MaterialChunk.user_id == user_id,
                MaterialChunk.course_id == course_id,
                MaterialChunk.embedding.is_not(None),
            )
        )
        return list(result.scalars().all())

    async def _database_hybrid_candidates(
        self,
        *,
        user_id: int | str,
        course_id: int | str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        material_scope: list[str] | None,
        metadata_filter: dict[str, Any] | None,
    ) -> list[tuple[Any, float]]:
        """Run both durable PostgreSQL retrieval legs and fuse by RRF.

        The application never rebuilds a lexical index in memory for this
        path.  PostgreSQL owns vector distance and full-text ranking, while
        the small application-side merge only combines the two ranked lists.
        """
        if MaterialChunk is None or Material is None or select is None or func is None:
            return []
        scope_predicate = []
        if material_scope:
            scope_predicate.append(Material.original_filename.in_(material_scope))
        dense_distance = MaterialChunk.embedding.cosine_distance(query_embedding).label(
            "distance"
        )
        dense_query = (
            select(MaterialChunk, dense_distance)
            .join(
                Material,
                (Material.id == MaterialChunk.material_id)
                & (Material.user_id == MaterialChunk.user_id)
                & (Material.course_id == MaterialChunk.course_id),
            )
            .where(
                MaterialChunk.user_id == user_id,
                MaterialChunk.course_id == course_id,
                MaterialChunk.embedding.is_not(None),
                *scope_predicate,
            )
            .order_by(dense_distance)
            .limit(top_k)
        )
        dense_rows = (await self._db_session.execute(dense_query)).all()

        lexical_rank = func.ts_rank(
            func.to_tsvector("simple", MaterialChunk.lexical_tokens),
            func.plainto_tsquery("simple", query),
        ).label("rank")
        lexical_query = (
            select(MaterialChunk, lexical_rank)
            .join(
                Material,
                (Material.id == MaterialChunk.material_id)
                & (Material.user_id == MaterialChunk.user_id)
                & (Material.course_id == MaterialChunk.course_id),
            )
            .where(
                MaterialChunk.user_id == user_id,
                MaterialChunk.course_id == course_id,
                func.to_tsvector("simple", MaterialChunk.lexical_tokens).op("@@")(
                    func.plainto_tsquery("simple", query)
                ),
                *scope_predicate,
            )
            .order_by(lexical_rank.desc())
            .limit(top_k)
        )
        lexical_rows = (await self._db_session.execute(lexical_query)).all()

        ranked: dict[str, tuple[Any, float]] = {}
        for rank, (row, _distance) in enumerate(dense_rows, start=1):
            metadata = dict(row.chunk_metadata or {})
            if not self._matches_metadata(metadata, metadata_filter):
                continue
            ranked[str(row.chunk_id)] = (row, 1.0 / (self._rrf_k + rank))
        for rank, (row, _score) in enumerate(lexical_rows, start=1):
            metadata = dict(row.chunk_metadata or {})
            if not self._matches_metadata(metadata, metadata_filter):
                continue
            chunk_id = str(row.chunk_id)
            contribution = 1.0 / (self._rrf_k + rank)
            if chunk_id in ranked:
                prior_row, prior_score = ranked[chunk_id]
                ranked[chunk_id] = (prior_row, prior_score + contribution)
            else:
                ranked[chunk_id] = (row, contribution)
        return sorted(ranked.values(), key=lambda item: item[1], reverse=True)[:top_k]

    @staticmethod
    def _cosine(query: Sequence[float], vector: Sequence[float] | None) -> float:
        if not vector:
            return 0.0
        try:
            dot = sum(float(a) * float(b) for a, b in zip(query, vector, strict=False))
            qnorm = math.sqrt(sum(float(a) ** 2 for a in query))
            vnorm = math.sqrt(sum(float(b) ** 2 for b in vector))
            return dot / (qnorm * vnorm) if qnorm and vnorm else 0.0
        except (TypeError, ValueError, OverflowError):
            return 0.0

    @staticmethod
    def _matches_metadata(metadata: dict[str, Any], metadata_filter: dict[str, Any] | None) -> bool:
        if not metadata_filter:
            return True
        for key, expected in metadata_filter.items():
            value = metadata.get(key)
            if isinstance(expected, dict) and "$in" in expected:
                if value not in expected["$in"]:
                    return False
            elif value != expected:
                return False
        return True

    def _make_evidence(
        self,
        row: Any,
        *,
        score: float,
        user_id: int | str,
        course_id: int | str | None,
    ) -> Evidence:
        chunk_id, text, metadata, _, _, raw = self._row_values(row)
        source = metadata.get("source") or metadata.get("filename")
        return Evidence(
            text=text,
            score=float(score),
            metadata=metadata,
            chunk_id=chunk_id,
            user_id=getattr(raw, "user_id", metadata.get("user_id", user_id)),
            course_id=getattr(raw, "course_id", metadata.get("course_id", course_id)),
            material_id=getattr(raw, "material_id", metadata.get("material_id")),
            source=source,
            page_number=getattr(raw, "page_number", metadata.get("page_number", metadata.get("page"))),
            slide_number=getattr(raw, "slide_number", metadata.get("slide_number")),
            section_title=getattr(raw, "section_title", metadata.get("section_title")),
            section_level=getattr(raw, "section_level", metadata.get("section_level")),
            char_start=getattr(raw, "char_start", metadata.get("char_start")),
            char_end=getattr(raw, "char_end", metadata.get("char_end")),
        )

    async def search(
        self,
        user_id: int | str,
        query: str,
        top_k: int = 10,
        metadata_filter: dict[str, Any] | None = None,
        course_id: int | str | None = None,
        material_scope: list[str] | None = None,
        apply_quality_gate: bool = True,
        **_: Any,
    ) -> RetrievalResponse:
        if top_k <= 0:
            return RetrievalResponse("no_results", [])
        if (self._uses_adapter or self._uses_database) and course_id is None:
            raise ValueError("course_id is required for database retrieval")
        embedding_service = self._get_embedding_service()
        query_embedding = embedding_service.embed_query(query)
        self._validate_embeddings([query_embedding], durable=self._uses_adapter or self._uses_database)

        if self._uses_adapter:
            rows = await self._adapter_rows()
            rows = [
                row
                for row in rows
                if getattr(row, "user_id", None) == user_id
                and getattr(row, "course_id", None) == course_id
            ]
        elif self._uses_database:
            rows = []
        else:
            filter_value = metadata_filter
            raw = self._get_vector_store().search(
                str(user_id), query_embedding, top_k=max(top_k * 4, top_k), metadata_filter=filter_value
            )
            rows = []
            for item in raw:
                item = dict(item)
                item.setdefault("chunk_id", item.get("id"))
                item.setdefault("text", item.get("document", ""))
                item.setdefault("embedding", None)
                rows.append(item)

        candidates: list[tuple[Any, float]] = []
        scope = set(material_scope or [])
        for row in rows:
            chunk_id, text, metadata, embedding, distance, _ = self._row_values(row)
            if (
                not self._uses_adapter
                and not self._uses_database
                and course_id is not None
                and metadata.get("course_id") != course_id
            ):
                continue
            if not self._matches_metadata(metadata, metadata_filter):
                continue
            source = metadata.get("source") or metadata.get("filename")
            if scope and source not in scope:
                continue
            dense = self._cosine(query_embedding, embedding)
            if embedding is None and distance is not None:
                dense = 1.0 - float(distance)
            lexical = self._lexical_score(query, text)
            candidates.append((row, 0.7 * dense + 0.3 * lexical))
        if self._uses_database:
            # The database branch already performed RRF. Preserve that order
            # and score instead of replacing it with an in-memory weighted
            # approximation before the cross-encoder stage.
            candidates = await self._database_hybrid_candidates(
                user_id=user_id,
                course_id=course_id,
                query=query,
                query_embedding=query_embedding,
                top_k=max(top_k * 4, top_k),
                material_scope=material_scope,
                metadata_filter=metadata_filter,
            )
        candidates.sort(key=lambda item: item[1], reverse=True)
        candidates = candidates[: max(top_k * 4, top_k)]
        if not candidates:
            return RetrievalResponse("no_results", [])

        reranker = self._get_reranker()
        pairs = [(query, self._row_values(row)[1]) for row, _ in candidates]
        try:
            rerank_scores = list(reranker.predict(pairs, show_progress_bar=False))
        except TypeError:
            rerank_scores = list(reranker.predict(pairs))
        scored = [
            (row, float(score)) for (row, _), score in zip(candidates, rerank_scores, strict=False)
        ]
        if not scored:
            return RetrievalResponse("no_results", [])
        if apply_quality_gate:
            kept = [(row, score) for row, score in scored if score >= self.quality_threshold]
            if not kept:
                return RetrievalResponse("quality_gate_failed", [])
        else:
            kept = scored
        kept.sort(key=lambda item: item[1], reverse=True)
        evidences = [
            self._make_evidence(row, score=score, user_id=user_id, course_id=course_id)
            for row, score in kept[:top_k]
        ]
        status = "ok" if len(evidences) >= top_k else "partial"
        return RetrievalResponse(status, evidences)

    @staticmethod
    def _lexical_score(query: str, text: str) -> float:
        terms = [term for term in query.lower().split() if term]
        if not terms:
            return 0.0
        lower = text.lower()
        return min(1.0, sum(term in lower for term in terms) / len(terms))


__all__ = ["Evidence", "RetrievalResponse", "RetrievalService", "SearchResult"]
