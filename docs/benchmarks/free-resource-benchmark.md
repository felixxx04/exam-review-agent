# Task 2.4 Free-Resource Benchmark

## Offline Contract Check

Run from `backend/`:

```powershell
python -m app.benchmarks.free_resource_benchmark --offline
pytest -q tests/test_free_resource_benchmark.py

# Remote SiliconFlow probe (reads the key only inside the benchmark process)
python -m app.benchmarks.free_resource_benchmark --siliconflow --task embedding --api-key-file <local-key-file>
python -m app.benchmarks.free_resource_benchmark --siliconflow --task reranker --api-key-file <local-key-file>
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
contract only.

On 2026-09-27, the available host reported approximately 1.9 GiB free physical
memory. Its existing Hugging Face cache contains about 2.7 GiB for
`BAAI/bge-large-zh-v1.5` and 1.1 GiB for `BAAI/bge-reranker-base`. Cold-loading
those models was not attempted because the available headroom is below the
cached artifact sizes. A smaller local model and a configured remote-compatible
endpoint still need real measurements before a provider can be selected.

Task 2.4 does not change `EmbeddingService`, `RetrievalService`, Chroma/BM25, or
production model defaults. PostgreSQL/pgvector retrieval remains a separate
Task 3.1 decision.

## Real Local Measurements (2026-09-28)

The repository fixture was measured in fresh Python processes on the local
Windows CPU host. The provider factory loaded each model inside the measured
process, so `first_load_ms` includes model construction. The fixture is only
two documents and two queries; its perfect quality score is a pipeline sanity
check, not a production quality estimate.

| Task | Provider | Artifact | First load | Throughput | Peak working set | Recall@1 | MRR |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Embedding | `BAAI/bge-small-zh-v1.5` | 96,405,966 bytes | 90.5 ms | 158.1 pages/s | 412.8 MB | 1.0 | 1.0 |
| Cross-Encoder | `BAAI/bge-reranker-base` | 1,134,408,930 bytes | 1,998.4 ms | 9.65 pages/s | 1,010.1 MB | 1.0 | 1.0 |

Both measurements used CPU inference, the cached immutable snapshot, and the
same fixture. These local results do not authorize a production model or
retrieval-path change.

## Remote SiliconFlow Measurements (2026-09-30 rerun)

The remote provider was measured in two fresh Python processes using the same
two-document, two-query fixture and `top_k=1`. The API key was read from a
local file by the CLI process and is not part of the report. `first_load_ms`
includes construction of the HTTP client; `pages_per_second` is the number of
fixture document or reranker candidate calls completed per second. Hosted
model aliases were used, so the revision is not pinned and these figures are
an endpoint snapshot rather than a reproducible model release benchmark.

| Task | Provider | Endpoint | First load | Throughput | Peak working set | Recall@1 | MRR |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Embedding | `BAAI/bge-m3` | `api.siliconflow.cn/v1/embeddings` | 278.9 ms | 2.193 pages/s | 42.63 MB | 1.0 | 1.0 |
| Cross-Encoder | `BAAI/bge-reranker-v2-m3` | `api.siliconflow.cn/v1/rerank` | 271.1 ms | 6.378 pages/s | 41.96 MB | 1.0 | 1.0 |

The rerun used fresh Python processes and returned no artifact size because hosted weights are not
available to the local process. Perfect quality on this two-item fixture only
proves that the provider adapter and benchmark pipeline agree; it is not a
production quality estimate. The provider remains benchmark-only and does not
change `EmbeddingService`, `RetrievalService`, Chroma/BM25, or PostgreSQL /
pgvector retrieval.

The benchmark key is read only inside the process from the supplied local file;
it is never printed or serialized into the report. This SiliconFlow key is
provider-specific and cannot be used for the separate DeepSeek chat smoke test.

For the local Docker setup used for this rerun, the existing `minio-temp`
container occupied ports 9000/9001. The managed service was started without
stopping it by overriding the published ports for that process:

```powershell
$env:MINIO_API_PORT='19000'
$env:MINIO_CONSOLE_PORT='19001'
docker compose --env-file .env up -d minio minio-init
```
