import pytest
from app.services.retrieval_service import RetrievalService, SearchResult


class _FakeVectorStore:
    def __init__(self):
        self.documents = []

    def add(self, user_id, embeddings, documents, metadatas, ids=None):
        self.documents.extend(
            {
                "id": doc_id,
                "document": document,
                "metadata": metadata,
                "distance": 0.1,
            }
            for doc_id, document, metadata in zip(ids, documents, metadatas, strict=False)
        )
        return ids

    def search(self, user_id, query_embedding, top_k=10, metadata_filter=None):
        results = self.documents
        if metadata_filter:
            for key, expected in metadata_filter.items():
                if isinstance(expected, dict) and "$in" in expected:
                    results = [
                        item for item in results
                        if item["metadata"].get(key) in expected["$in"]
                    ]
                else:
                    results = [
                        item for item in results
                        if item["metadata"].get(key) == expected
                    ]
        return results[:top_k]

    def delete(self, user_id, ids):
        self.documents = [item for item in self.documents if item["id"] not in ids]


class _FakeEmbeddingService:
    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0]


class _FakeCrossEncoder:
    def predict(self, pairs, show_progress_bar=False):
        return [0.9 for _ in pairs]


@pytest.mark.asyncio
async def test_hybrid_search_returns_ranked_results():
    service = RetrievalService()
    await service.index_chunks("test-user", [
        {"text": "薛定谔方程描述量子态随时间的演化", "metadata": {"source": "quantum.pdf", "page": 23}},
        {"text": "矩阵的特征值是满足det(A-λI)=0的λ", "metadata": {"source": "linalg.pdf", "page": 45}},
    ])
    results = await service.search("test-user", "什么是薛定谔方程", top_k=2)
    assert len(results) >= 1
    assert "薛定" in results[0].text


@pytest.mark.asyncio
async def test_search_result_has_required_fields():
    service = RetrievalService()
    await service.index_chunks("test-user-fields", [
        {"text": "量子力学的基本原理包括波粒二象性", "metadata": {"source": "physics.pdf", "page": 10}},
    ])
    results = await service.search("test-user-fields", "量子力学", top_k=1)
    assert len(results) == 1
    assert isinstance(results[0], SearchResult)
    assert hasattr(results[0], "text")
    assert hasattr(results[0], "score")
    assert hasattr(results[0], "metadata")
    assert results[0].score > 0.0


@pytest.mark.asyncio
async def test_index_and_delete_chunks():
    service = RetrievalService()
    chunk_ids = await service.index_chunks("test-user-del", [
        {"text": "测试内容一", "metadata": {"source": "test.pdf", "page": 1}},
        {"text": "测试内容二", "metadata": {"source": "test.pdf", "page": 2}},
    ])
    assert len(chunk_ids) == 2
    await service.delete_chunks("test-user-del", chunk_ids)
    results = await service.search("test-user-del", "测试内容", top_k=5)
    assert all(r.metadata.get("chunk_id") not in chunk_ids for r in results)


@pytest.mark.asyncio
async def test_search_with_quality_gate_filters_low_relevance():
    service = RetrievalService(quality_threshold=0.5)
    await service.index_chunks("test-user-gate", [
        {"text": "Java是一种面向对象的编程语言", "metadata": {"source": "cs.pdf", "page": 1}},
    ])
    results = await service.search("test-user-gate", "原核生物学中的CRISPR技术", top_k=5)
    # Highly irrelevant results should be filtered by the quality gate
    for r in results:
        assert r.score >= 0.5


@pytest.mark.asyncio
async def test_metadata_filtering_in_search():
    service = RetrievalService()
    await service.index_chunks("test-user-filter", [
        {"text": "线性代数的基本概念", "metadata": {"source": "linalg.pdf", "page": 1}},
        {"text": "概率论中的贝叶斯公式", "metadata": {"source": "prob.pdf", "page": 15}},
    ])
    results = await service.search(
        "test-user-filter", "数学", top_k=5,
        metadata_filter={"source": "linalg.pdf"}
    )
    assert len(results) >= 1
    for r in results:
        assert r.metadata.get("source") == "linalg.pdf"


@pytest.mark.asyncio
async def test_metadata_filtering_applies_to_bm25_results(monkeypatch):
    monkeypatch.setattr(
        RetrievalService,
        "_get_cross_encoder",
        classmethod(lambda cls: _FakeCrossEncoder()),
    )
    service = RetrievalService(
        vector_store=_FakeVectorStore(),
        embedding_service=_FakeEmbeddingService(),
    )
    await service.index_chunks("test-user-bm25-filter", [
        {"text": "公共主题 当前资料内容", "metadata": {"source": "current.pdf"}},
        {"text": "公共主题 旧资料内容", "metadata": {"source": "old.pdf"}},
    ])

    results = await service.search(
        "test-user-bm25-filter",
        "公共主题",
        top_k=5,
        metadata_filter={"source": {"$in": ["current.pdf"]}},
    )

    assert len(results) >= 1
    assert {r.metadata.get("source") for r in results} == {"current.pdf"}


@pytest.mark.asyncio
async def test_batch_index_large_documents():
    service = RetrievalService()
    chunks = [
        {"text": f"文档片段 {i} 的内容，涉及人工智能和机器学习的基本原理", "metadata": {"source": "ai.pdf", "page": i // 5 + 1}}
        for i in range(10)
    ]
    chunk_ids = await service.index_chunks("test-user-batch", chunks)
    assert len(chunk_ids) == 10
    results = await service.search("test-user-batch", "机器学习", top_k=5)
    assert len(results) >= 1
