---
name: rag-hybrid-retrieval
description: Implement hybrid RAG retrieval combining BM25 keyword search, dense vector search, and cross-encoder reranking for high-quality document retrieval. Use this skill when building RAG systems, implementing search over documents, or whenever the user mentions "RAG", "retrieval", "vector search", "hybrid search", "reranking", or "document Q&A". Also use when retrieval quality matters — pure vector search often misses keyword-exact matches.
---

# Hybrid RAG Retrieval

Pure vector search misses keyword-exact matches. Pure keyword search misses semantic similarity. Hybrid retrieval combines both and reranks for the best of both worlds.

Based on patterns from hello-agents Chapter 8 (`05_RAGTool_Advanced_Search.py`, `10_RAG_Pipeline_Complete.py`).

## The Three-Stage Pipeline

```
Query
  │
  ├──→ BM25 Search (keyword matching)  ──→ candidates_k ──┐
  │                                                        ├──→ Reranker ──→ top_k
  └──→ Dense Search (semantic matching) ──→ candidates_k ──┘
```

### Stage 1: Dual Retrieval

```python
def hybrid_search(query: str, top_k: int = 10) -> list[Chunk]:
    # BM25: exact keyword matches (great for names, terms, formulas)
    bm25_results = bm25_search(query, top_k=top_k)

    # Dense: semantic similarity (great for conceptual questions)
    dense_results = vector_search(query, top_k=top_k)

    # Merge and deduplicate
    merged = merge_and_dedup(bm25_results, dense_results)
    return merged
```

**Why both?** A query like "计算矩阵特征值" needs BM25 for "特征值" (exact term) AND dense for "矩阵运算方法" (semantic neighbor).

### Stage 2: Cross-Encoder Reranking

BM25 and dense search use bi-encoders (query and document encoded separately). A cross-encoder encodes query+document together for more accurate relevance scoring.

```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder("BAAI/bge-reranker-base")

def rerank(query: str, candidates: list[Chunk], top_k: int = 5) -> list[Chunk]:
    pairs = [(query, chunk.text) for chunk in candidates]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return [chunk for chunk, score in ranked[:top_k]]
```

### Stage 3: Quality-Gated Output

Before passing results to the LLM, validate retrieval quality:

```python
def search_with_guard(query: str, top_k: int = 5) -> list[Chunk]:
    candidates = hybrid_search(query, top_k=top_k * 3)
    ranked = rerank(query, candidates, top_k=top_k)

    # Guard: refuse if no results meet relevance threshold
    if not ranked or ranked[0].score < RELEVANCE_THRESHOLD:
        raise InsufficientMaterialError(
            "上传的资料中未找到相关内容，请确认资料是否覆盖该主题"
        )
    return ranked
```

## Advanced Retrieval Strategies

### Multi-Query Expansion (MQE)

For ambiguous queries, generate multiple search queries:

```python
def multi_query_search(user_query: str, n_variants: int = 3) -> list[Chunk]:
    variants = llm.generate(f"将以下问题改写为{n_variants}个不同角度的搜索查询: {user_query}")
    all_results = []
    for variant in variants:
        all_results.extend(hybrid_search(variant))
    return rerank(user_query, dedup(all_results))
```

### Hypothetical Document Embeddings (HyDE)

Generate a hypothetical answer, then search for documents similar to that answer:

```python
def hyde_search(query: str) -> list[Chunk]:
    hypothetical_answer = llm.generate(f"请回答: {query}")
    return vector_search(hypothetical_answer)  # Search with the answer, not the question
```

## Chunking Strategy

Semantic chunking > fixed token count:

- Split by section headers (chapter, section, subsection)
- Keep each chunk as one coherent concept
- Store metadata: `chapter`, `page`, `heading`, `source_file`
- Use overlap windows (50-100 tokens) at chunk boundaries to prevent concept splitting

```python
chunk = Chunk(
    text="...",
    metadata={
        "source": "量子力学.pdf",
        "chapter": "第三章",
        "page": 23,
        "heading": "薛定谔方程",
    }
)
```

## RAGTool Action-Dispatch Pattern

A single class interface for all RAG operations:

```python
class RAGTool:
    def run(self, params: dict) -> str:
        action = params["action"]
        if action == "add_text":
            return self._add_text(params["text"], params["metadata"])
        elif action == "search":
            return self._search(params["query"], params["top_k"])
        elif action == "ask":
            return self._ask(params["question"])
        else:
            raise ValueError(f"Unknown action: {action}")
```

This keeps the RAG subsystem behind one API while supporting multiple operations.

## Source

Derived from hello-agents Chapter 8 RAG implementations and the LearningAgent project's retrieval patterns.
