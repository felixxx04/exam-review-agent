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


@pytest.mark.parametrize(
    "payload",
    [
        {"data": [{"index": 0, "embedding": [1.0]}, {"index": 0, "embedding": [2.0]}]},
        {"data": [{"index": 0, "embedding": [1.0]}, {"index": 2, "embedding": [2.0]}]},
        {"data": [{"index": 0, "embedding": [1.0]}, {"index": 1, "embedding": [float("nan")]}]},
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
        [{"index": 0, "relevance_score": float("inf")}, {"index": 1, "relevance_score": 0.0}],
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


def test_provider_requires_nonempty_api_key():
    module = _provider_module()

    with pytest.raises(ValueError, match="API key"):
        module.SiliconFlowEmbeddingProvider(" ")
