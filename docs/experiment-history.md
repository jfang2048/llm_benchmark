# Experiment History

The workspace evolved through several benchmark generations before converging
on the controlled model comparison published in `results/final/`. This page
summarizes that evolution so readers understand what changed and why only the
final run is published. The raw historical directories are **not** committed.

## Generations

### 1. Early A/B deployment benchmark (`bench_llm.sh`)

The first script compared two *deployments*: `spark-x25` (Spark-X2.5-4B on
llama.cpp) vs `vllm` (Qwen3 on vLLM). It already enforced fairness (same raw
prompts, `temperature=0`, `ignore_eos=true`, one server at a time), but it
compared **different models on different engines**, so it could not isolate a
single variable. Superseded.

### 2. Engine cross-benchmark (`cross_benchmark.sh` → `_v7`)

The cross-benchmark series compared **backends** while pinning the model where
possible:

- `qwen_llama` — Qwen3-4B-Q4_K_M on llama.cpp
- `qwen_vllm_gguf` — Qwen3-4B-Q4_K_M on vLLM (GGUF plugin)
- `qwen_vllm_awq` — Qwen3-4B-AWQ on vLLM
- `spark_llama` — Spark-X2.5-4B-Q4_K_M on llama.cpp

It introduced input-sequence-length sweeps (512, 2048) and the AIPerf
`--isl`/`--apply-chat-template` path for the Qwen-only engine comparison. The
AWQ arm required the HF cache; GGUF support required the plugin; several early
runs captured startup failures while these were debugged.

### 3. Model benchmark (`model_benchmark_v8.sh` → `v11_diag.sh`)

The final generation isolated the **model** variable by fixing the engine to
llama.cpp and the quantization to Q4_K_M, then comparing Spark-X2.5-4B against
Qwen3-4B under identical serving flags. Later versions added:

- a runtime-control equivalence gate (`verify_runtime_controls`) proving both
  arms run the same image and the same flags;
- an AIPerf sanity gate (one request per arm before the full matrix);
- crossover A/B ordering to reduce temporal/thermal bias;
- C=3 to test whether the Qwen C=2 throughput collapse was a real
  scheduling/batching discontinuity;
- classified error extraction (`error_details.tsv`) and a `runtime_config.txt`.

`v11_diag` is the published methodology, reproduced by `scripts/benchmark.sh`.

### 4. Reliability-gated benchmark

The historical run's `ServerDisconnectedError` rates showed the v1 methodology
was not trustworthy enough to rank models. The measurement was rebuilt in
stages (see `docs/methodology.md` for the current design):

- Root-caused the transport failures (client-side aiohttp pooled connection
  reuse vs the llama.cpp server closing keep-alive connections), fixed with
  `--connection-reuse-strategy never`, and added a hard gate
  (≥ 99.5% transport success, `FORCE_UNSTABLE=1` marks `INVALID_FOR_RANKING`).
- Added the result schema and terminology (`pass/unstable/failed/parsed` runs,
  successful-request-only latency).
- Added suites: capacity, shape, open-loop, startup, soak, sessions, backend,
  plus a GPU-side energy estimate and a v2 dashboard.

Each suite is a `make benchmark-<name>` target; results land under
`results/v2/` (git-ignored raw runs plus committed curated data). The v1 final
run is kept only as historical diagnostic provenance.

## Why the historical directories are not published

- `benchmark/results/` — early AIPerf runs against the everyday 8000/8001
  deployments (mixed methodology).
- `benchmark/results-cross/` — engine-comparison runs, many of which were
  startup/debug iterations rather than clean experiments.
- `benchmark/results-model/` — model-comparison runs; only `20260904_192416`
  (the final, fully controlled run) is published.
- `benchmark/inventory/` — raw `docker inspect` dumps and logs (may contain
  environment variables; not publishable).
- `vllm-qwen3/bench-results/` — raw AIPerf JSON from the vLLM RPS sweep.

These remain available locally for provenance but are excluded from Git.
