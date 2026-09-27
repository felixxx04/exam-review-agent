# Task 2.4 Free-Resource Benchmark

## Offline Contract Check

Run from `backend/`:

```powershell
python -m app.benchmarks.free_resource_benchmark --offline
pytest -q tests/test_free_resource_benchmark.py
```

The offline command uses fixed fixture providers. Its timing and memory figures
are runner diagnostics only; they are not model performance measurements and
must not be used to choose a production provider.

## Provider Comparison

`BenchmarkRunner` accepts an injected provider factory, so the benchmark does
not import production retrieval services or make network calls. Provider
methods may be synchronous or asynchronous; asynchronous methods are driven in
a fresh event loop by the synchronous runner, which therefore must not be
called from inside an existing event loop.
For each local or remote-compatible configuration:

1. Provide a `ProviderSpec` with provider kind, model ID, immutable version,
   embedding dimension (when applicable), and endpoint for remote providers.
2. Ensure the factory fully loads the provider before returning it. For a fair
   cold-start measurement, run each configuration in a fresh process and let
   the factory use only cached weights. Remote calls require an explicitly
   supplied provider and endpoint; the runner itself never sends a request.
3. Use the same labelled documents, query set, candidate count, and top-k for
   all configurations. Record the generated JSON unchanged with the machine,
   Python, CPU/GPU, OS, and model cache revision.

The report contains model artifact bytes when the provider or spec supplies
them, first-load milliseconds, document pages per second, process peak working
set (Windows) or peak RSS (Unix), Recall@k, MRR, and query count. The memory
metric is the process high-water mark, so isolated fresh-process runs are
required when comparing providers. Model size may be taken from an explicit
`model_size_bytes` option or the recursive size of a local `model_path`.

## Current Evidence

The fixture contract passes for both local and remote-compatible Embedding and
Cross-Encoder provider specs, including model identity, output dimension,
retrieval quality, and report serialization. This validates the measurement
contract only. No real local model or remote endpoint result is recorded here.

On 2026-09-27, the available host reported approximately 1.9 GiB free physical
memory. Its existing Hugging Face cache contains about 2.7 GiB for
`BAAI/bge-large-zh-v1.5` and 1.1 GiB for `BAAI/bge-reranker-base`. Cold-loading
those models was not attempted because the available headroom is below the
cached artifact sizes. A smaller local model and a configured remote-compatible
endpoint still need real measurements before a provider can be selected.

Task 2.4 does not change `EmbeddingService`, `RetrievalService`, Chroma/BM25, or
production model defaults. PostgreSQL/pgvector retrieval remains a separate
Task 3.1 decision.
