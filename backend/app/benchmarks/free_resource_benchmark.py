"""Reproducible resource probes for pluggable embedding and reranker providers.

The runner is deliberately independent of ``RetrievalService``.  It can measure
an injected local provider or an injected remote-compatible provider without
opening a network connection itself.
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import inspect
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Sequence

ProviderKind = Literal["local", "remote"]
ProviderFactory = Callable[[], object]


@dataclass(frozen=True)
class ProviderSpec:
    """Metadata required to compare providers without inspecting their objects."""

    name: str
    kind: ProviderKind
    model_id: str
    version: str
    dimension: int | None = None
    endpoint: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if self.kind not in ("local", "remote"):
            raise ValueError("kind must be local or remote")
        if not self.model_id.strip():
            raise ValueError("model_id must not be empty")
        if not self.version.strip():
            raise ValueError("version must not be empty")
        if self.dimension is not None and self.dimension <= 0:
            raise ValueError("dimension must be positive")
        if self.kind == "remote" and not (self.endpoint or "").strip():
            raise ValueError("remote providers require endpoint")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "model_id": self.model_id,
            "version": self.version,
            "dimension": self.dimension,
            "endpoint": self.endpoint,
            "options": dict(self.options),
        }


@dataclass(frozen=True)
class BenchmarkDocument:
    id: str
    text: str

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("document id must not be empty")
        if not self.text.strip():
            raise ValueError("document text must not be empty")


@dataclass(frozen=True)
class BenchmarkQuery:
    id: str
    text: str
    relevant_document_ids: frozenset[str]

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("query id must not be empty")
        if not self.text.strip():
            raise ValueError("query text must not be empty")
        if not self.relevant_document_ids:
            raise ValueError("query must have at least one relevant document")


@dataclass(frozen=True)
class BenchmarkDataset:
    documents: tuple[BenchmarkDocument, ...]
    queries: tuple[BenchmarkQuery, ...]

    def __post_init__(self) -> None:
        document_ids = [document.id for document in self.documents]
        query_ids = [query.id for query in self.queries]
        if not document_ids or not query_ids:
            raise ValueError("benchmark dataset must contain documents and queries")
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document ids must be unique")
        if len(query_ids) != len(set(query_ids)):
            raise ValueError("query ids must be unique")
        unknown = set().union(
            *(query.relevant_document_ids for query in self.queries)
        ) - set(document_ids)
        if unknown:
            raise ValueError(f"queries reference unknown documents: {sorted(unknown)}")


@dataclass(frozen=True)
class QualityMetrics:
    recall_at_k: float
    mrr: float
    evaluated_queries: int


@dataclass(frozen=True)
class ResourceMetrics:
    model_size_bytes: int | None
    first_load_ms: float
    pages_per_second: float
    peak_memory_mb: float
    memory_measurement: str = "process_peak_resident_memory"


@dataclass(frozen=True)
class BenchmarkResult:
    provider: ProviderSpec
    task: Literal["embedding", "reranker"]
    top_k: int
    metrics: ResourceMetrics
    quality: QualityMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider.to_dict(),
            "task": self.task,
            "top_k": self.top_k,
            "metrics": asdict(self.metrics),
            "quality": asdict(self.quality),
        }


class BenchmarkRunner:
    """Run deterministic provider probes over a small labelled page fixture."""

    def __init__(
        self,
        dataset: BenchmarkDataset,
        *,
        top_k: int = 5,
        repeats: int = 1,
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if repeats <= 0:
            raise ValueError("repeats must be positive")
        self.dataset = dataset
        self.top_k = min(top_k, len(dataset.documents))
        self.repeats = repeats

    def run_embedding(
        self,
        spec: ProviderSpec,
        provider_factory: ProviderFactory,
    ) -> BenchmarkResult:
        provider, first_load_ms = self._load(provider_factory)
        return _run_sync(self._run_embedding(provider, spec, first_load_ms))

    async def _run_embedding(
        self, provider: object, spec: ProviderSpec, first_load_ms: float
    ) -> BenchmarkResult:
        document_texts = [document.text for document in self.dataset.documents]
        started = time.perf_counter()
        document_vectors: list[list[float]] = []
        for _ in range(self.repeats):
            document_vectors = await _await_result(
                _call_embedding_documents(provider, document_texts)
            )
        elapsed = max(time.perf_counter() - started, 1e-9)
        self._validate_dimension(spec, document_vectors)

        query_vectors = [
            await _await_result(_call_embedding_query(provider, query.text))
            for query in self.dataset.queries
        ]
        rankings = []
        for query_vector in query_vectors:
            rankings.append(
                _rank_by_scores(
                    [
                        _cosine_similarity(query_vector, document_vector)
                        for document_vector in document_vectors
                    ],
                    [document.id for document in self.dataset.documents],
                )
            )
        peak_memory_mb = _peak_process_memory_mb()
        return BenchmarkResult(
            provider=spec,
            task="embedding",
            top_k=self.top_k,
            metrics=ResourceMetrics(
                model_size_bytes=_model_size_bytes(provider, spec),
                first_load_ms=first_load_ms,
                pages_per_second=(len(self.dataset.documents) * self.repeats) / elapsed,
                peak_memory_mb=peak_memory_mb,
            ),
            quality=_quality_metrics(rankings, self.dataset.queries, self.top_k),
        )

    def run_reranker(
        self,
        spec: ProviderSpec,
        provider_factory: ProviderFactory,
    ) -> BenchmarkResult:
        provider, first_load_ms = self._load(provider_factory)
        return _run_sync(self._run_reranker(provider, spec, first_load_ms))

    async def _run_reranker(
        self, provider: object, spec: ProviderSpec, first_load_ms: float
    ) -> BenchmarkResult:
        documents = [document.text for document in self.dataset.documents]
        rankings = []
        started = time.perf_counter()
        for query in self.dataset.queries:
            scores: Sequence[float] = ()
            for _ in range(self.repeats):
                scores = await _await_result(
                    _call_reranker(provider, query.text, documents)
                )
            if len(scores) != len(documents):
                raise ValueError("reranker must return one score per document")
            rankings.append(
                _rank_by_scores(
                    scores, [document.id for document in self.dataset.documents]
                )
            )
        elapsed = max(time.perf_counter() - started, 1e-9)
        peak_memory_mb = _peak_process_memory_mb()
        return BenchmarkResult(
            provider=spec,
            task="reranker",
            top_k=self.top_k,
            metrics=ResourceMetrics(
                model_size_bytes=_model_size_bytes(provider, spec),
                first_load_ms=first_load_ms,
                pages_per_second=(
                    len(documents) * len(self.dataset.queries) * self.repeats
                )
                / elapsed,
                peak_memory_mb=peak_memory_mb,
            ),
            quality=_quality_metrics(rankings, self.dataset.queries, self.top_k),
        )

    @staticmethod
    def _load(provider_factory: ProviderFactory) -> tuple[object, float]:
        started = time.perf_counter()
        provider = provider_factory()
        first_load_ms = (time.perf_counter() - started) * 1000
        return provider, first_load_ms

    @staticmethod
    def _validate_dimension(
        spec: ProviderSpec, vectors: Sequence[Sequence[float]]
    ) -> None:
        if not vectors:
            raise ValueError("embedding provider returned no vectors")
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise ValueError("embedding provider returned inconsistent dimensions")
        if spec.dimension is not None and dimensions != {spec.dimension}:
            raise ValueError("embedding dimension does not match provider spec")


def _call_embedding_documents(provider: object, texts: list[str]) -> Any:
    method = getattr(provider, "embed_documents", None) or getattr(
        provider, "embed", None
    )
    if method is None:
        raise TypeError("embedding provider must expose embed_documents or embed")
    return method(texts)


def _call_embedding_query(provider: object, text: str) -> Any:
    method = getattr(provider, "embed_query", None)
    if method is not None:
        return method(text)
    return _call_embedding_documents(provider, [text])[0]


def _call_reranker(provider: object, query: str, documents: list[str]) -> Any:
    score = getattr(provider, "score", None)
    if score is not None:
        return score(query, documents)
    predict = getattr(provider, "predict", None)
    if predict is not None:
        return predict(
            [(query, document) for document in documents], show_progress_bar=False
        )
    raise TypeError("reranker provider must expose score or predict")


async def _await_result(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _run_sync(value: Any) -> Any:
    if inspect.isawaitable(value):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(value)
        close = getattr(value, "close", None)
        if close is not None:
            close()
        raise TypeError("benchmark runner cannot be called from a running event loop")
    return value


def _model_size_bytes(provider: object, spec: ProviderSpec) -> int | None:
    value = getattr(provider, "model_size_bytes", None)
    if value is None:
        value = spec.options.get("model_size_bytes")
    if value is None:
        model_path = spec.options.get("model_path")
        if model_path:
            path = Path(str(model_path))
            if path.is_file():
                return path.stat().st_size
            if path.is_dir():
                return sum(
                    item.stat().st_size for item in path.rglob("*") if item.is_file()
                )
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("model_size_bytes must be a non-negative integer")
    return value


def _peak_process_memory_mb() -> float:
    """Return the operating system's process high-water resident memory."""
    if os.name == "nt":

        class ProcessMemoryCountersEx(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCountersEx()
        counters.cb = ctypes.sizeof(counters)
        get_current_process = ctypes.windll.kernel32.GetCurrentProcess
        get_current_process.restype = ctypes.c_void_p
        process = get_current_process()
        get_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_memory_info.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ProcessMemoryCountersEx),
            ctypes.c_ulong,
        ]
        get_memory_info.restype = ctypes.c_int
        if not get_memory_info(process, ctypes.byref(counters), counters.cb):
            raise OSError("GetProcessMemoryInfo failed")
        peak_bytes = counters.PeakWorkingSetSize
    else:
        import resource
        import sys

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_bytes = peak if sys.platform == "darwin" else peak * 1024
    return peak_bytes / (1024 * 1024)


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding vectors have different dimensions")
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _rank_by_scores(scores: Sequence[float], ids: Sequence[str]) -> list[str]:
    return [
        document_id
        for _, document_id in sorted(
            zip(scores, ids, strict=True), key=lambda item: (-float(item[0]), item[1])
        )
    ]


def _quality_metrics(
    rankings: Sequence[Sequence[str]],
    queries: Sequence[BenchmarkQuery],
    top_k: int,
) -> QualityMetrics:
    reciprocal_ranks: list[float] = []
    total_hits = 0
    total_relevant = 0
    for ranking, query in zip(rankings, queries, strict=True):
        limited = list(ranking[:top_k])
        total_hits += len(set(limited) & query.relevant_document_ids)
        total_relevant += len(query.relevant_document_ids)
        reciprocal_rank = 0.0
        for index, document_id in enumerate(limited, start=1):
            if document_id in query.relevant_document_ids:
                reciprocal_rank = 1.0 / index
                break
        reciprocal_ranks.append(reciprocal_rank)
    count = len(queries)
    return QualityMetrics(
        recall_at_k=total_hits / total_relevant if total_relevant else 0.0,
        mrr=sum(reciprocal_ranks) / count if count else 0.0,
        evaluated_queries=count,
    )


def offline_dataset() -> BenchmarkDataset:
    return BenchmarkDataset(
        documents=(
            BenchmarkDocument("physics", "量子力学基础"),
            BenchmarkDocument("network", "计算机网络基础"),
        ),
        queries=(
            BenchmarkQuery("q1", "量子", frozenset({"physics"})),
            BenchmarkQuery("q2", "网络", frozenset({"network"})),
        ),
    )


class _OfflineEmbeddingProvider:
    model_id = "fixture/offline-embedding"
    dimension = 2
    model_size_bytes = 2048

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        return [1.0, 0.0] if "量子" in text else [0.0, 1.0]


class _OfflineRerankerProvider:
    model_id = "fixture/offline-reranker"
    model_size_bytes = 1024

    def score(self, query: str, documents: list[str]) -> list[float]:
        return [1.0 if query in document else 0.0 for document in documents]


def offline_report() -> list[dict[str, Any]]:
    """Run the no-network fixture suite used by CI and local verification."""
    runner = BenchmarkRunner(offline_dataset(), top_k=1)
    local_embedding = ProviderSpec(
        name="offline-local-embedding",
        kind="local",
        model_id="fixture/offline-embedding",
        version="1",
        dimension=2,
    )
    remote_embedding = ProviderSpec(
        name="offline-remote-embedding",
        kind="remote",
        model_id="fixture/offline-embedding",
        version="1",
        dimension=2,
        endpoint="offline://fixture",
    )
    local_reranker = ProviderSpec(
        name="offline-local-reranker",
        kind="local",
        model_id="fixture/offline-reranker",
        version="1",
    )
    remote_reranker = ProviderSpec(
        name="offline-remote-reranker",
        kind="remote",
        model_id="fixture/offline-reranker",
        version="1",
        endpoint="offline://fixture",
    )
    results = [
        runner.run_embedding(local_embedding, _OfflineEmbeddingProvider),
        runner.run_embedding(remote_embedding, _OfflineEmbeddingProvider),
        runner.run_reranker(local_reranker, _OfflineRerankerProvider),
        runner.run_reranker(remote_reranker, _OfflineRerankerProvider),
    ]
    return [result.to_dict() for result in results]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run offline or explicit SiliconFlow free-resource benchmarks"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="run deterministic fixture providers without network access",
    )
    parser.add_argument(
        "--siliconflow",
        action="store_true",
        help="run one real remote provider against the fixed fixture",
    )
    parser.add_argument(
        "--task",
        choices=("embedding", "reranker"),
        help="remote task to measure in this process",
    )
    parser.add_argument(
        "--api-key-file",
        type=Path,
        help="read the SiliconFlow API key from a local file",
    )
    args = parser.parse_args()
    if args.siliconflow:
        if args.offline:
            parser.error("--offline and --siliconflow cannot be combined")
        if args.task is None:
            parser.error("--siliconflow requires --task")
        if args.api_key_file is None:
            parser.error("--siliconflow requires --api-key-file")
        try:
            api_key = args.api_key_file.read_text(encoding="utf-8-sig").strip()
        except OSError:
            parser.error("unable to read the SiliconFlow API key file")
        if not api_key:
            parser.error("the SiliconFlow API key file is empty")
        from app.benchmarks.siliconflow_provider import siliconflow_report

        report = siliconflow_report(api_key, args.task)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if args.api_key_file is not None or args.task is not None:
        parser.error("--task and --api-key-file require --siliconflow")
    if not args.offline:
        parser.error(
            "select --offline or configure --siliconflow for a real remote probe"
        )
    print(json.dumps(offline_report(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
