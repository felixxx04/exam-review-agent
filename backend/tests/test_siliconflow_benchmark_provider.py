import importlib

import httpx
import pytest


def _provider_module():
    return importlib.import_module("app.benchmarks.siliconflow_provider")


def _mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_embedding_provider_sends_authorized_request_and_restores_input_order():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        )

    module = _provider_module()
    provider = module.SiliconFlowEmbeddingProvider(
        "secret-token",
        client=_mock_client(respond),
    )

    vectors = provider.embed_documents(["量子力学基础", "计算机网络基础"])

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert requests[0].url == "https://api.siliconflow.cn/v1/embeddings"
    assert requests[0].headers["authorization"] == "Bearer secret-token"
    assert requests[0].read() == (
        b'{"model":"BAAI/bge-m3","input":["\xe9\x87\x8f\xe5\xad\x90\xe5\x8a\x9b\xe5\xad\xa6\xe5\x9f\xba\xe7\xa1\x80",'
        b'"\xe8\xae\xa1\xe7\xae\x97\xe6\x9c\xba\xe7\xbd\x91\xe7\xbb\x9c\xe5\x9f\xba\xe7\xa1\x80"],"encoding_format":"float"}'
    )


def test_embedding_query_uses_single_vector_response():
    client = _mock_client(
        lambda request: httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.25, 0.75]}]},
        )
    )
    provider = _provider_module().SiliconFlowEmbeddingProvider(
        "secret-token", client=client
    )

    assert provider.embed_query("网络") == [0.25, 0.75]


def test_providers_skip_network_for_empty_inputs():
    def fail(request):
        raise AssertionError("empty inputs must not call SiliconFlow")

    client = _mock_client(fail)
    embedding = _provider_module().SiliconFlowEmbeddingProvider(
        "secret-token", client=client
    )
    reranker = _provider_module().SiliconFlowRerankerProvider(
        "secret-token", client=client
    )

    assert embedding.embed_documents([]) == []
    assert reranker.score("量子", []) == []


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [{"index": 0, "embedding": [1.0]}, {"index": 0, "embedding": [2.0]}]},
        {"data": [{"index": 0, "embedding": [1.0]}, {"index": 2, "embedding": [2.0]}]},
        {"data": [{"index": 0, "embedding": [1.0]}]},
    ],
)
def test_embedding_provider_rejects_invalid_or_incomplete_vectors(payload):
    provider = _provider_module().SiliconFlowEmbeddingProvider(
        "secret-token",
        client=_mock_client(lambda request: httpx.Response(200, json=payload)),
    )

    with pytest.raises(ValueError):
        provider.embed_documents(["量子", "网络"])


def test_embedding_provider_rejects_non_finite_vector_after_adapter_validation():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            content=b'{"data":[{"index":0,"embedding":[NaN]},'
            b'{"index":1,"embedding":[0.0]}]}',
        )

    provider = _provider_module().SiliconFlowEmbeddingProvider(
        "secret-token", client=_mock_client(respond)
    )

    with pytest.raises(ValueError, match="non-finite embedding vector"):
        provider.embed_documents(["量子", "网络"])

    assert len(requests) == 1


def test_embedding_provider_rejects_http_errors_without_leaking_token():
    provider = _provider_module().SiliconFlowEmbeddingProvider(
        "secret-token",
        client=_mock_client(
            lambda request: httpx.Response(401, text="secret-token rejected")
        ),
    )

    with pytest.raises(RuntimeError) as exc_info:
        provider.embed_documents(["量子"])

    assert "secret-token" not in str(exc_info.value)
    assert "401" in str(exc_info.value)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json=[]),
    ],
)
def test_provider_rejects_malformed_success_response(response):
    provider = _provider_module().SiliconFlowEmbeddingProvider(
        "secret-token", client=_mock_client(lambda request: response)
    )

    with pytest.raises(ValueError):
        provider.embed_documents(["量子"])


def test_provider_maps_transport_failures_to_sanitized_error():
    def fail(request):
        raise httpx.ConnectError("secret-token leaked by transport")

    provider = _provider_module().SiliconFlowEmbeddingProvider(
        "secret-token", client=_mock_client(fail)
    )

    with pytest.raises(RuntimeError, match="request failed") as exc_info:
        provider.embed_documents(["量子"])

    assert "secret-token" not in str(exc_info.value)


def test_reranker_provider_sends_all_candidates_and_restores_document_order():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.2},
                    {"index": 0, "relevance_score": 0.9},
                ]
            },
        )

    provider = _provider_module().SiliconFlowRerankerProvider(
        "secret-token", client=_mock_client(respond)
    )

    scores = provider.score("量子", ["量子力学基础", "计算机网络基础"])

    assert scores == [0.9, 0.2]
    assert requests[0].url == "https://api.siliconflow.cn/v1/rerank"
    assert requests[0].headers["authorization"] == "Bearer secret-token"
    assert requests[0].read() == (
        b'{"model":"BAAI/bge-reranker-v2-m3","query":"\xe9\x87\x8f\xe5\xad\x90",'
        b'"documents":["\xe9\x87\x8f\xe5\xad\x90\xe5\x8a\x9b\xe5\xad\xa6\xe5\x9f\xba\xe7\xa1\x80",'
        b'"\xe8\xae\xa1\xe7\xae\x97\xe6\x9c\xba\xe7\xbd\x91\xe7\xbb\x9c\xe5\x9f\xba\xe7\xa1\x80"],'
        b'"top_n":2,"return_documents":false}'
    )


@pytest.mark.parametrize(
    "results",
    [
        [{"index": 0, "relevance_score": 1.0}, {"index": 0, "relevance_score": 0.0}],
        [{"index": 0, "relevance_score": 1.0}, {"index": 2, "relevance_score": 0.0}],
        [{"index": 0, "relevance_score": 1.0}],
    ],
)
def test_reranker_provider_rejects_invalid_or_incomplete_scores(results):
    provider = _provider_module().SiliconFlowRerankerProvider(
        "secret-token",
        client=_mock_client(
            lambda request: httpx.Response(200, json={"results": results})
        ),
    )

    with pytest.raises(ValueError):
        provider.score("量子", ["量子力学基础", "计算机网络基础"])


def test_reranker_provider_rejects_non_finite_score_after_adapter_validation():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            content=b'{"results":[{"index":0,"relevance_score":Infinity},'
            b'{"index":1,"relevance_score":0.0}]}',
        )

    provider = _provider_module().SiliconFlowRerankerProvider(
        "secret-token", client=_mock_client(respond)
    )

    with pytest.raises(ValueError, match="non-finite relevance score"):
        provider.score("量子", ["量子力学基础", "计算机网络基础"])

    assert len(requests) == 1


def test_provider_requires_nonempty_api_key():
    module = _provider_module()

    with pytest.raises(ValueError, match="API key"):
        module.SiliconFlowEmbeddingProvider(" ")


def test_siliconflow_report_constructs_provider_inside_measured_factory(monkeypatch):
    module = _provider_module()
    created = []

    class FakeEmbedding:
        model_id = module.EMBEDDING_MODEL
        dimension = 1024

        def __init__(self, api_key):
            created.append(api_key)

        def embed_documents(self, texts):
            return [self._vector(text) for text in texts]

        def embed_query(self, text):
            return self._vector(text)

        @staticmethod
        def _vector(text):
            return (
                ([1.0] + [0.0] * 1023)
                if "量子" in text
                else ([0.0] + [1.0] + [0.0] * 1022)
            )

        def close(self):
            pass

    monkeypatch.setattr(module, "SiliconFlowEmbeddingProvider", FakeEmbedding)

    report = module.siliconflow_report("secret-token", "embedding")

    assert created == ["secret-token"]
    assert report[0]["quality"]["recall_at_k"] == 1.0


def test_siliconflow_report_rejects_unknown_task():
    with pytest.raises(ValueError, match="task"):
        _provider_module().siliconflow_report("secret-token", "unknown")


def test_siliconflow_report_constructs_reranker_inside_measured_factory(monkeypatch):
    module = _provider_module()
    created = []

    class FakeReranker:
        model_id = module.RERANK_MODEL

        def __init__(self, api_key):
            created.append(api_key)

        def score(self, query, documents):
            return [1.0 if query in document else 0.0 for document in documents]

        def close(self):
            pass

    monkeypatch.setattr(module, "SiliconFlowRerankerProvider", FakeReranker)

    report = module.siliconflow_report("secret-token", "reranker")

    assert created == ["secret-token"]
    assert report[0]["task"] == "reranker"
    assert report[0]["quality"]["recall_at_k"] == 1.0


def test_siliconflow_report_closes_provider_when_benchmark_fails(monkeypatch):
    module = _provider_module()
    closed = []

    class FailingEmbedding:
        def __init__(self, api_key):
            pass

        def embed_documents(self, texts):
            raise RuntimeError("remote failure")

        def close(self):
            closed.append(True)

    monkeypatch.setattr(module, "SiliconFlowEmbeddingProvider", FailingEmbedding)

    with pytest.raises(RuntimeError, match="remote failure"):
        module.siliconflow_report("secret-token", "embedding")

    assert closed == [True]
