import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.db.vector_store import VectorStore
from app.services.embedding_service import EmbeddingService


@dataclass
class SearchResult:
    text: str
    score: float
    metadata: dict = field(default_factory=dict)


class RetrievalService:
    """Hybrid retrieval service: BM25 + dense + cross-encoder rerank + quality gate."""

    _cross_encoder = None
    _cross_encoder_name: str = "BAAI/bge-reranker-base"

    def __init__(
        self,
        quality_threshold: float = 0.3,
        rrf_k: int = 60,
        vector_store: Optional[VectorStore] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ):
        self._quality_threshold = quality_threshold
        self._rrf_k = rrf_k
        self._vector_store = vector_store or VectorStore()
        self._embedding_service = embedding_service
        self._bm25_indices: dict[str, tuple[BM25Okapi, list[str], list[dict], list[str]]] = {}

    # ------------------------------------------------------------------
    # Cross-encoder (lazy singleton)
    # ------------------------------------------------------------------

    @classmethod
    def _get_cross_encoder(cls):
        if cls._cross_encoder is None:
            from sentence_transformers import CrossEncoder

            cls._cross_encoder = CrossEncoder(cls._cross_encoder_name)
        return cls._cross_encoder

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    async def index_chunks(
        self,
        user_id: str,
        chunks: list[dict],
    ) -> list[str]:
        """Index chunks into the vector store and BM25 index.

        Each chunk dict must have: text, metadata (optional)
        Returns list of chunk IDs.
        """
        texts = [chunk["text"] for chunk in chunks]
        metadatas = [chunk.get("metadata", {}) for chunk in chunks]

        # Generate embeddings
        embeddings = self._get_embedding_service().embed_documents(texts)

        # Add embedding chunk_id to metadata for tracking
        chunk_ids = [str(uuid.uuid4()) for _ in chunks]
        for i, cid in enumerate(chunk_ids):
            metadatas[i] = {**metadatas[i], "chunk_id": cid}

        # Store in vector DB
        self._vector_store.add(
            user_id=user_id,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
            ids=chunk_ids,
        )

        # Update BM25 index
        tokenized = [self._tokenize(t) for t in texts]
        if user_id in self._bm25_indices:
            old_bm25, old_texts, old_metas, old_ids = self._bm25_indices[user_id]
            combined_texts = old_texts + texts
            combined_metas = old_metas + metadatas
            combined_ids = old_ids + chunk_ids
            combined_tokens = [self._tokenize(t) for t in combined_texts]
            self._bm25_indices[user_id] = (
                BM25Okapi(combined_tokens),
                combined_texts,
                combined_metas,
                combined_ids,
            )
        else:
            self._bm25_indices[user_id] = (
                BM25Okapi(tokenized),
                texts,
                metadatas,
                chunk_ids,
            )

        return chunk_ids

    # ------------------------------------------------------------------
    # Search pipeline
    # ------------------------------------------------------------------

    async def search(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        metadata_filter: Optional[dict] = None,
        apply_quality_gate: bool = True,
    ) -> list[SearchResult]:
        """Hybrid search: BM25 + dense vector search + RRF fusion + rerank + quality gate."""
        # 1. Dual retrieval
        bm25_results = self._bm25_search(user_id, query, top_k * 2, metadata_filter)
        dense_results = self._dense_search(user_id, query, top_k * 2, metadata_filter)

        # 2. Reciprocal rank fusion (RRF)
        fused = self._rrf_fusion(bm25_results, dense_results, top_k * 2)

        # 3. Cross-encoder reranking
        reranked = self._rerank(query, fused, top_k)

        # 4. Quality gate
        results = []
        for item in reranked:
            if not apply_quality_gate or item["score"] >= self._quality_threshold:
                results.append(
                    SearchResult(
                        text=item["text"],
                        score=item["score"],
                        metadata=item["metadata"],
                    )
                )

        return results[:top_k]

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    async def delete_chunks(self, user_id: str, chunk_ids: list[str]) -> None:
        """Delete chunks from both stores."""
        self._vector_store.delete(user_id, chunk_ids)
        if user_id in self._bm25_indices:
            bm25, texts, metas, ids = self._bm25_indices[user_id]
            keep_indices = [i for i, cid in enumerate(ids) if cid not in chunk_ids]
            if keep_indices:
                new_texts = [texts[i] for i in keep_indices]
                new_metas = [metas[i] for i in keep_indices]
                new_ids = [ids[i] for i in keep_indices]
                tokenized = [self._tokenize(t) for t in new_texts]
                self._bm25_indices[user_id] = (BM25Okapi(tokenized), new_texts, new_metas, new_ids)
            else:
                del self._bm25_indices[user_id]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_embedding_service(self) -> EmbeddingService:
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService()
        return self._embedding_service

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple character-level tokenization for Chinese text."""
        # For Chinese text, character-level tokenization works well with BM25
        tokens = []
        for ch in text:
            if ch.strip():
                tokens.append(ch)
            else:
                tokens.append(ch)
        return tokens

    def _bm25_search(
        self,
        user_id: str,
        query: str,
        top_k: int,
        metadata_filter: Optional[dict] = None,
    ) -> list[dict]:
        """BM25 keyword search."""
        if user_id not in self._bm25_indices:
            return []
        bm25, texts, metas, ids = self._bm25_indices[user_id]
        query_tokens = self._tokenize(query)
        scores = bm25.get_scores(query_tokens)
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] > 0 and self._metadata_matches(metas[idx], metadata_filter):
                results.append({
                    "text": texts[idx],
                    "metadata": metas[idx],
                    "id": ids[idx],
                    "score": float(scores[idx]),
                    "source": "bm25",
                })
        return results

    @staticmethod
    def _metadata_matches(metadata: dict, metadata_filter: Optional[dict]) -> bool:
        """Apply the Chroma-style filters used by the app to BM25 results too."""
        if not metadata_filter:
            return True

        for key, expected in metadata_filter.items():
            actual = metadata.get(key)
            if isinstance(expected, dict):
                if "$in" in expected and actual not in expected["$in"]:
                    return False
            elif actual != expected:
                return False
        return True

    def _dense_search(
        self, user_id: str, query: str, top_k: int, metadata_filter: Optional[dict] = None
    ) -> list[dict]:
        """Dense vector search via ChromaDB."""
        query_embedding = self._get_embedding_service().embed_query(query)
        raw_results = self._vector_store.search(
            user_id, query_embedding, top_k, metadata_filter
        )
        results = []
        for item in raw_results:
            similarity = 1.0 - item["distance"]
            results.append({
                "text": item["document"],
                "metadata": item["metadata"],
                "id": item["id"],
                "score": float(similarity),
                "source": "dense",
            })
        return results

    def _rrf_fusion(
        self,
        bm25_results: list[dict],
        dense_results: list[dict],
        top_k: int,
    ) -> list[dict]:
        """Reciprocal rank fusion combining BM25 and dense results."""
        rrf_scores: dict[str, dict] = {}
        for rank, item in enumerate(bm25_results):
            doc_id = item["id"]
            rrf = 1.0 / (self._rrf_k + rank + 1)
            if doc_id in rrf_scores:
                rrf_scores[doc_id]["score"] += rrf
            else:
                rrf_scores[doc_id] = {**item, "score": rrf}
        for rank, item in enumerate(dense_results):
            doc_id = item["id"]
            rrf = 1.0 / (self._rrf_k + rank + 1)
            if doc_id in rrf_scores:
                rrf_scores[doc_id]["score"] += rrf
            else:
                rrf_scores[doc_id] = {**item, "score": rrf}
        sorted_items = sorted(rrf_scores.values(), key=lambda x: x["score"], reverse=True)
        return sorted_items[:top_k]

    def _rerank(
        self, query: str, candidates: list[dict], top_k: int
    ) -> list[dict]:
        """Cross-encoder reranking."""
        if not candidates:
            return []
        cross_encoder = self._get_cross_encoder()
        pairs = [(query, item["text"]) for item in candidates]
        scores = cross_encoder.predict(pairs, show_progress_bar=False)
        if isinstance(scores, np.ndarray):
            scores = scores.tolist()
        for i, score in enumerate(scores):
            candidates[i]["score"] = float(score)
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_k]
