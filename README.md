# Local LLM Inference Benchmark

A reproducible benchmark for local LLM inference on a constrained consumer GPU
(NVIDIA RTX 3060 Laptop, 6 GiB VRAM). It compares ~4B-class models in Q4_K_M
quantization served by the same llama.cpp engine, under identical runtime
settings and an identical workload.

> **Dashboard:** https://jfang2048.github.io/llm_benchmark/
>
> **Benchmark v2 dashboard:** https://jfang2048.github.io/llm_benchmark/v2/

## What this repository does

- Defines a controlled serving benchmark methodology
  ([docs/methodology.md](docs/methodology.md)).
- Provides reproducible Docker builds for llama.cpp (with Spark-X2.5 support)
  and vLLM.
- Provides one-command deployment and benchmarking via `make`.
- Publishes a curated, sanitized dataset under `results/v2/final/`.
- Generates static dashboards and charts from committed data — every displayed
  number is derived from machine-readable `.tsv` files.

## Models

| Model | Quantization | Parameters |
|---|---|---|
| Spark-X2.5-4B | Q4_K_M | 4B |
| Qwen3-4B | Q4_K_M | 4B |

## Test system

| Component | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 3060 Laptop GPU, 6144 MiB VRAM |
| Driver / CUDA | 610.74 / 13.3 |
| CPU | AMD Ryzen 7 6800H (16 logical CPUs) |
| Platform | WSL2, Ubuntu 24.04 |
| Docker | 29.7.2 |
| Engine | llama.cpp (XHToken fork for Spark-X2.5 support), CUDA 13.3 build |
| Benchmark tool | NVIDIA AIPerf 0.12.0 |

## Quick start

```bash
git clone https://github.com/jfang2048/llm_benchmark.git
cd llm_benchmark
make preflight      # validate GPU, Docker, ports, models
make setup          # download models + build images
make deploy         # create serving containers
make healthcheck    # verify endpoints
make benchmark      # run the benchmark
make report         # rebuild the dashboard
```

## Benchmark suites

Each suite is a `make benchmark-<name>` target writing results under
`results/v2/`:

- `capacity` — closed-loop throughput/error sweep vs concurrency.
- `shape` — token-controlled ISL/OSL workload sweep.
- `open-loop` — Poisson load sweep with SLO/goodput compliance.
- `startup` — process cold-start latency.
- `soak` — sustained load + thermal degradation.
- `sessions` — multi-turn latency by turn.
- `backend` — engine comparison (same Qwen GGUF on llama.cpp vs vLLM+GGUF).

Transport reliability is gated: a run must reach ≥ 99.5% request success before
its results are presented as a ranking; `FORCE_UNSTABLE=1` overrides this and
marks the run `INVALID_FOR_RANKING`.

## Reproduce

```bash
make reproduce
```

Runs preflight → download → build → deploy → healthcheck → benchmark → report.
Idempotent: existing models and images are reused. Use
`REPRODUCE_MODE=smoke ./scripts/reproduce.sh` for a fast validation path.

> Qwen3-4B-Q4_K_M downloads from the official Qwen GGUF repo.
> Spark-X2.5-4B-Q4_K_M has no canonical public GGUF URL — see
> [models/README.md](models/README.md) for acquisition paths. Both are verified
> against pinned SHA256 hashes.

## Methodology

See [docs/methodology.md](docs/methodology.md) for the design, metric
definitions (TTFT, ITL, E2E latency, throughput, error rate), aggregation, and
limitations.

## Data

- Current dataset: [`results/v2/`](results/v2/README.md)
- Historical v1 (diagnostic): [`docs/history/v1.md`](docs/history/v1.md)

## Limitations

- One GPU, one laptop, one driver version — representative of this exact
  environment, not a general ranking.
- Serving cost, not model quality (accuracy/reasoning).
- Cross-model tokens/s is secondary because the tokenizers differ.

## License

No source-code license is asserted for this repository. Model weights are
governed by their own upstream licenses (Qwen3, Spark-X2.5) and are not
redistributed here.

## Security

Model weights, caches, credentials, raw Docker inspection dumps, and private
machine paths are excluded (see `.gitignore`). A pre-push gate
(`./scripts/security_check.sh`, also run in CI) checks for secrets, private
paths, oversized files, and non-English text.
