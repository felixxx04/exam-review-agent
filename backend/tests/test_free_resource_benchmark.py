import asyncio

import pytest

from app.benchmarks import free_resource_benchmark as benchmark
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
        return [1.0 if query in document else 0.0 for document in documents]


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
    assert payload["metrics"]["memory_measurement"] == "process_peak_resident_memory"
    assert "provider_instance" not in payload


def test_dataset_rejects_queries_for_unknown_documents():
    with pytest.raises(ValueError, match="unknown documents"):
        BenchmarkDataset(
            documents=(BenchmarkDocument("known", "已知资料"),),
            queries=(BenchmarkQuery("q", "问题", frozenset({"missing"})),),
        )


def test_embedding_benchmark_rejects_dimension_mismatch(dataset):
    class WrongDimensionProvider(_FakeEmbeddingProvider):
        def embed_documents(self, texts):
            return [[1.0] for _ in texts]

    with pytest.raises(ValueError, match="dimension does not match"):
        BenchmarkRunner(dataset).run_embedding(
            ProviderSpec(
                name="wrong-dimension",
                kind="local",
                model_id="fixture/wrong-dimension",
                version="1",
                dimension=2,
            ),
            WrongDimensionProvider,
        )


def test_remote_provider_requires_endpoint():
    with pytest.raises(ValueError, match="require endpoint"):
        ProviderSpec(
            name="remote",
            kind="remote",
            model_id="remote/model",
            version="1",
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": "", "kind": "local", "model_id": "m", "version": "1"}, "name"),
        (
            {"name": "p", "kind": "local", "model_id": "m", "version": ""},
            "version",
        ),
        (
            {
                "name": "p",
                "kind": "local",
                "model_id": "m",
                "version": "1",
                "dimension": 0,
            },
            "dimension",
        ),
    ],
)
def test_provider_spec_rejects_invalid_fields(kwargs, message):
    with pytest.raises(ValueError, match=message):
        ProviderSpec(**kwargs)


def test_runner_rejects_invalid_limits(dataset):
    with pytest.raises(ValueError, match="top_k"):
        BenchmarkRunner(dataset, top_k=0)
    with pytest.raises(ValueError, match="repeats"):
        BenchmarkRunner(dataset, repeats=0)


def test_dataset_requires_unique_document_and_query_ids():
    with pytest.raises(ValueError, match="document ids"):
        BenchmarkDataset(
            documents=(
                BenchmarkDocument("same", "第一份"),
                BenchmarkDocument("same", "第二份"),
            ),
            queries=(BenchmarkQuery("q", "問題", frozenset({"same"})),),
        )


def test_embedding_accepts_legacy_embed_method_and_checks_vector_dimensions(dataset):
    class LegacyEmbeddingProvider:
        model_size_bytes = None

        def embed(self, texts):
            return [[1.0, 0.0] for _ in texts]

    result = BenchmarkRunner(dataset).run_embedding(
        ProviderSpec(
            name="legacy",
            kind="local",
            model_id="fixture/legacy",
            version="1",
            dimension=2,
        ),
        LegacyEmbeddingProvider,
    )
    assert result.quality.evaluated_queries == 2

    class InconsistentEmbeddingProvider:
        def embed_documents(self, texts):
            return [[1.0], [1.0, 0.0]]

    with pytest.raises(ValueError, match="inconsistent dimensions"):
        BenchmarkRunner(dataset).run_embedding(
            ProviderSpec(
                name="inconsistent",
                kind="local",
                model_id="fixture/inconsistent",
                version="1",
            ),
            InconsistentEmbeddingProvider,
        )


def test_embedding_benchmark_supports_async_remote_compatible_provider(dataset):
    class AsyncEmbeddingProvider:
        model_size_bytes = 4096

        def __init__(self):
            self.loops = []

        async def embed_documents(self, texts):
            self.loops.append(asyncio.get_running_loop())
            return [[1.0, 0.0] if "量子" in text else [0.0, 1.0] for text in texts]

        async def embed_query(self, text):
            self.loops.append(asyncio.get_running_loop())
            return [1.0, 0.0] if "量子" in text else [0.0, 1.0]

    provider = AsyncEmbeddingProvider()
    result = BenchmarkRunner(dataset).run_embedding(
        ProviderSpec(
            name="async-remote-compatible",
            kind="remote",
            model_id="fixture/async-embedding",
            version="1",
            dimension=2,
            endpoint="offline://async-fixture",
        ),
        lambda: provider,
    )
    assert result.metrics.model_size_bytes == 4096
    assert result.quality.recall_at_k == 1.0
    assert provider.loops
    assert all(loop is provider.loops[0] for loop in provider.loops)


@pytest.mark.asyncio
async def test_runner_rejects_call_inside_existing_event_loop(dataset):
    class AsyncEmbeddingProvider:
        async def embed_documents(self, texts):
            return [[1.0, 0.0] for _ in texts]

        async def embed_query(self, text):
            return [1.0, 0.0]

    with pytest.raises(TypeError, match="running event loop"):
        BenchmarkRunner(dataset).run_embedding(
            ProviderSpec(
                name="async",
                kind="local",
                model_id="fixture/async",
                version="1",
                dimension=2,
            ),
            AsyncEmbeddingProvider,
        )


def test_reranker_rejects_wrong_number_of_scores(dataset):
    class ShortReranker:
        def score(self, query, documents):
            return [1.0]

    with pytest.raises(ValueError, match="one score per document"):
        BenchmarkRunner(dataset).run_reranker(
            ProviderSpec(
                name="short",
                kind="local",
                model_id="fixture/short",
                version="1",
            ),
            ShortReranker,
        )


def test_model_size_can_be_measured_from_path(tmp_path, dataset):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "weights.bin").write_bytes(b"weights")
    (model_dir / "config.json").write_bytes(b"{}")

    class PathProvider:
        def embed_documents(self, texts):
            return [[1.0, 0.0] if "量子" in text else [0.0, 1.0] for text in texts]

        def embed_query(self, text):
            return [1.0, 0.0] if "量子" in text else [0.0, 1.0]

    result = BenchmarkRunner(dataset).run_embedding(
        ProviderSpec(
            name="path-model",
            kind="local",
            model_id="fixture/path-model",
            version="1",
            dimension=2,
            options={"model_path": str(model_dir)},
        ),
        PathProvider,
    )
    assert result.metrics.model_size_bytes == 9


def test_invalid_model_size_is_rejected(dataset):
    class InvalidSizeProvider(_FakeEmbeddingProvider):
        model_size_bytes = -1

    with pytest.raises(ValueError, match="non-negative integer"):
        BenchmarkRunner(dataset).run_embedding(
            ProviderSpec(
                name="bad-size",
                kind="local",
                model_id="fixture/bad-size",
                version="1",
                dimension=2,
            ),
            InvalidSizeProvider,
        )


def test_offline_command_is_explicit_and_emits_four_provider_results(
    monkeypatch, capsys
):
    monkeypatch.setattr("sys.argv", ["benchmark", "--offline"])
    benchmark.main()
    payload = capsys.readouterr().out
    assert payload.count('"task":') == 4

    monkeypatch.setattr("sys.argv", ["benchmark"])
    with pytest.raises(SystemExit) as error:
        benchmark.main()
    assert error.value.code == 2
