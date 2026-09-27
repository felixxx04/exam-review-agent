import pytest

from app.benchmarks.free_resource_benchmark import (
    BenchmarkDataset,
    BenchmarkDocument,
    BenchmarkQuery,
    BenchmarkRunner,
    ProviderSpec,
)


class _FakeEmbeddingProvider:
    model_id = "fixture/embedding"
    dimension = 2
    model_size_bytes = 2048

    def embed_documents(self, texts):
        return [self._vector(text) for text in texts]

    def embed_query(self, text):
        return self._vector(text)

    @staticmethod
    def _vector(text):
        return [1.0, 0.0] if "量子" in text else [0.0, 1.0]


class _FakeRerankerProvider:
    model_id = "fixture/reranker"
    model_size_bytes = 1024

    def score(self, query, documents):
        return [1.0 if "量子" in document else 0.0 for document in documents]


@pytest.fixture
def dataset():
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


def test_provider_spec_requires_identity_and_supports_remote_configuration():
    local = ProviderSpec(
        name="fixture-local",
        kind="local",
        model_id="fixture/embedding",
        version="1",
        dimension=2,
    )
    remote = ProviderSpec(
        name="fixture-remote",
        kind="remote",
        model_id="remote/embedding",
        version="2026-01",
        dimension=2,
        endpoint="https://example.invalid/embeddings",
    )

    assert local.kind == "local"
    assert remote.endpoint == "https://example.invalid/embeddings"

    with pytest.raises(ValueError, match="model_id"):
        ProviderSpec(name="missing-model", kind="local", model_id="", version="1")


def test_embedding_benchmark_reports_resources_and_retrieval_quality(dataset):
    result = BenchmarkRunner(dataset, top_k=1).run_embedding(
        ProviderSpec(
            name="fixture-local",
            kind="local",
            model_id="fixture/embedding",
            version="1",
            dimension=2,
        ),
        _FakeEmbeddingProvider,
    )

    assert result.provider.name == "fixture-local"
    assert result.metrics.model_size_bytes == 2048
    assert result.metrics.first_load_ms >= 0
    assert result.metrics.pages_per_second > 0
    assert result.metrics.peak_memory_mb >= 0
    assert result.quality.recall_at_k == 1.0
    assert result.quality.mrr == 1.0
    assert result.quality.evaluated_queries == 2


def test_reranker_benchmark_uses_injected_provider_without_network(dataset):
    result = BenchmarkRunner(dataset, top_k=1).run_reranker(
        ProviderSpec(
            name="fixture-remote",
            kind="remote",
            model_id="fixture/reranker",
            version="1",
            endpoint="offline://fixture",
        ),
        _FakeRerankerProvider,
    )

    assert result.provider.kind == "remote"
    assert result.metrics.model_size_bytes == 1024
    assert result.metrics.pages_per_second > 0
    assert result.quality.recall_at_k == 1.0
    assert result.quality.mrr == 1.0


def test_report_is_json_serializable_and_does_not_include_provider_objects(dataset):
    result = BenchmarkRunner(dataset).run_embedding(
        ProviderSpec(
            name="fixture-local",
            kind="local",
            model_id="fixture/embedding",
            version="1",
            dimension=2,
        ),
        _FakeEmbeddingProvider,
    )

    payload = result.to_dict()

    assert payload["provider"]["model_id"] == "fixture/embedding"
    assert payload["metrics"]["peak_memory_mb"] >= 0
    assert "provider_instance" not in payload
