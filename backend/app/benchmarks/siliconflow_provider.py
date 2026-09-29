"""SiliconFlow HTTP providers used only by the resource benchmark harness."""

from __future__ import annotations

import math
from typing import Any, Sequence

import httpx

EMBEDDING_ENDPOINT = "https://api.siliconflow.cn/v1/embeddings"
RERANK_ENDPOINT = "https://api.siliconflow.cn/v1/rerank"
EMBEDDING_MODEL = "BAAI/bge-m3"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"


class _SiliconFlowClient:
    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("SiliconFlow API key must not be empty")
        self._endpoint = endpoint
        self._client = client or httpx.Client(timeout=timeout)
        self._headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        }

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(
                self._endpoint,
                headers=self._headers,
                json=payload,
            )
        except httpx.TimeoutException:
            raise RuntimeError("SiliconFlow request timed out") from None
        except httpx.RequestError:
            raise RuntimeError("SiliconFlow request failed") from None
        if response.is_error:
            raise RuntimeError(
                f"SiliconFlow request failed with HTTP {response.status_code}"
            )
        try:
            data = response.json()
        except ValueError:
            raise ValueError("SiliconFlow returned invalid JSON") from None
        if not isinstance(data, dict):
            raise ValueError("SiliconFlow response must be an object")
        return data

    def close(self) -> None:
        self._client.close()


class SiliconFlowEmbeddingProvider(_SiliconFlowClient):
    model_id = EMBEDDING_MODEL
    dimension = 1024

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(
            api_key,
            endpoint=EMBEDDING_ENDPOINT,
            client=client,
            timeout=timeout,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = self._post(
            {
                "model": self.model_id,
                "input": texts,
                "encoding_format": "float",
            }
        )
        rows = payload.get("data")
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise ValueError("SiliconFlow returned an incomplete embedding batch")
        vectors: list[list[float] | None] = [None] * len(texts)
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("SiliconFlow returned an invalid embedding row")
            index = _validated_index(row.get("index"), len(texts))
            if vectors[index] is not None:
                raise ValueError("SiliconFlow returned duplicate embedding indexes")
            raw_vector = row.get("embedding")
            if not isinstance(raw_vector, list) or not raw_vector:
                raise ValueError("SiliconFlow returned an invalid embedding vector")
            vector = _validated_numbers(raw_vector, "embedding vector")
            vectors[index] = vector
        if any(vector is None for vector in vectors):
            raise ValueError("SiliconFlow returned an incomplete embedding batch")
        completed = [vector for vector in vectors if vector is not None]
        if len({len(vector) for vector in completed}) != 1:
            raise ValueError("SiliconFlow returned inconsistent embedding dimensions")
        return completed

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        if not vectors:
            raise ValueError("SiliconFlow returned no query embedding")
        return vectors[0]


class SiliconFlowRerankerProvider(_SiliconFlowClient):
    model_id = RERANK_MODEL

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(
            api_key,
            endpoint=RERANK_ENDPOINT,
            client=client,
            timeout=timeout,
        )

    def score(self, query: str, documents: list[str]) -> list[float]:
        if not documents:
            return []
        payload = self._post(
            {
                "model": self.model_id,
                "query": query,
                "documents": documents,
                "top_n": len(documents),
                "return_documents": False,
            }
        )
        rows = payload.get("results")
        if not isinstance(rows, list) or len(rows) != len(documents):
            raise ValueError("SiliconFlow returned an incomplete rerank result")
        scores: list[float | None] = [None] * len(documents)
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("SiliconFlow returned an invalid rerank row")
            index = _validated_index(row.get("index"), len(documents))
            if scores[index] is not None:
                raise ValueError("SiliconFlow returned duplicate rerank indexes")
            score = _validated_numbers([row.get("relevance_score")], "relevance score")[
                0
            ]
            scores[index] = score
        if any(score is None for score in scores):
            raise ValueError("SiliconFlow returned an incomplete rerank result")
        return [score for score in scores if score is not None]


def _validated_index(value: Any, count: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < count:
        raise ValueError("SiliconFlow returned an invalid result index")
    return value


def _validated_numbers(values: Sequence[Any], label: str) -> list[float]:
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float))
        for value in values
    ):
        raise ValueError(f"SiliconFlow returned an invalid {label}")
    numbers = [float(value) for value in values]
    if not all(math.isfinite(value) for value in numbers):
        raise ValueError(f"SiliconFlow returned a non-finite {label}")
    return numbers


def siliconflow_report(api_key: str, task: str) -> list[dict[str, Any]]:
    """Run one task against the shared offline fixture in an isolated process."""
    from app.benchmarks.free_resource_benchmark import (
        BenchmarkRunner,
        ProviderSpec,
        offline_dataset,
    )

    if task not in {"embedding", "reranker"}:
        raise ValueError("task must be embedding or reranker")
    runner = BenchmarkRunner(offline_dataset(), top_k=1)
    if task == "embedding":
        providers: list[SiliconFlowEmbeddingProvider] = []

        def factory() -> SiliconFlowEmbeddingProvider:
            provider = SiliconFlowEmbeddingProvider(api_key)
            providers.append(provider)
            return provider

        spec = ProviderSpec(
            name="siliconflow-bge-m3",
            kind="remote",
            model_id=EMBEDDING_MODEL,
            version="hosted alias (revision not pinned)",
            dimension=1024,
            endpoint=EMBEDDING_ENDPOINT,
        )
        try:
            result = runner.run_embedding(spec, factory)
        finally:
            for provider in providers:
                provider.close()
    else:
        providers: list[SiliconFlowRerankerProvider] = []

        def factory() -> SiliconFlowRerankerProvider:
            provider = SiliconFlowRerankerProvider(api_key)
            providers.append(provider)
            return provider

        spec = ProviderSpec(
            name="siliconflow-bge-reranker-v2-m3",
            kind="remote",
            model_id=RERANK_MODEL,
            version="hosted alias (revision not pinned)",
            endpoint=RERANK_ENDPOINT,
        )
        try:
            result = runner.run_reranker(spec, factory)
        finally:
            for provider in providers:
                provider.close()
    return [result.to_dict()]
