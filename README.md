# Local LLM Inference Benchmark

A reproducible benchmark for local LLM inference serving on a constrained
consumer GPU (NVIDIA RTX 3060 Laptop, 6 GiB VRAM). The current primary cohort
is four mainstream 8-9B dense open-weight models in IQ4_XS quantization, all
served by the same pinned upstream llama.cpp build under an identical resource
policy and workload. The earlier ~4B cohort is preserved as historical data.

> **Dashboard:** https://jfang2048.github.io/llm_benchmark/

## What this repository does

- Defines a controlled fixed-hardware deployment benchmark
  ([docs/methodology.md](docs/methodology.md)): it measures serving
  performance under one GPU/engine/quantization policy, not model quality.
- Provides a pinned, reproducible upstream llama.cpp Docker build
  (`docker/llama-cpp-upstream/`, tag v0.4.0, CUDA arch 86).
- Derives the active model set and sweep parameters from a single registry
  (`configs/models.json` + `configs/benchmark.json`); the runner and report
  generator read from it, never from hardcoded model lists.
- Runs the benchmark through a small registry-driven harness (`bench/`) with
  AIPerf as the client.
- Publishes a curated, sanitized dataset under `results/current/` and renders
  a static dashboard from it — every displayed number comes from
  machine-readable `.tsv` files.

## Models (current primary cohort)

| Model | Parameters | Quantization | License |
|---|---|---|---|
| Qwen3-8B | 8.19B | IQ4_XS | Apache-2.0 |
| DeepSeek-R1-Distill-Llama-8B | 8.03B | IQ4_XS | MIT |
| GLM-4-9B-0414 | 9.40B | IQ4_XS | MIT |
| Yi-1.5-9B-Chat | 8.83B | IQ4_XS | Apache-2.0 |

All four are served as IQ4_XS GGUF (single uniform source, SHA256 recorded in
`configs/models.json`) by the same pinned upstream `ggml-org/llama.cpp`
build. `DeepSeek-R1-Distill-Llama-8B` is a DeepSeek-distilled Llama-3.1-8B
dense model — not the DeepSeek-R1/V3 MoE architecture.

## Test system

| Component | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 3060 Laptop GPU, 6144 MiB VRAM |
| CPU | AMD Ryzen 7 6800H |
| Platform | WSL2, Ubuntu 24.04 |
| Engine | ggml-org/llama.cpp, pinned tag v0.4.0 (CUDA arch 86) |
| Serving policy | `--ctx-size 4096 --parallel 2 --n-gpu-layers 999 --cont-batching` |
| Benchmark tool | NVIDIA AIPerf 0.12.0 |

## Quick start

```bash
git clone https://github.com/jfang2048/llm_benchmark.git
cd llm_benchmark
make preflight             # validate GPU, Docker, models
# acquire the 4 IQ4_XS GGUFs into models/ (see models/README.md), then:
docker build -t llama-cpp-upstream:v0.4.0 -f docker/llama-cpp-upstream/Dockerfile docker/llama-cpp-upstream/
./scripts/admit_8b9b.sh    # serve + healthcheck + smoke + VRAM admission
make benchmark-8b9b        # capacity sweep (registry-driven)
make report-current        # rebuild docs/current/index.html
```

## Benchmark suites

Run via the registry-driven harness (`bench/runner.py`); `make` targets wrap it.

- `make benchmark-8b9b` — capacity: closed-loop throughput/latency/error sweep
  vs concurrency (1/2/4/6/8, 60 req/cell, 3 repeats, rotated model order).
- `make reliability-8b9b` — transport-reliability gate (≥200 requests, Wilson
  95% CI on success rate, error classification).
- `make shape-8b9b` — token-controlled ISL/OSL workload sweep.
- `make llama-bench` — raw-engine microbenchmark (pp512/tg128) with the same
  binary; kept separate from the AIPerf end-to-end serving numbers.

Serving is gated on a per-model admission test (`scripts/admit_8b9b.sh`):
healthcheck, a generation request, a 20-request smoke test, and a VRAM/OOM
check before a model enters the benchmark. Capacity results with `FAILED` or
`UNSTABLE` cells are never presented as valid ranking points.

## Reproduce

```bash
make reproduce
```

## Methodology

See [docs/methodology.md](docs/methodology.md) for metric definitions (TTFT,
ITL, E2E latency, throughput, goodput), aggregation, and limitations. This is
a fixed-hardware deployment benchmark: numbers are representative of this
exact GPU/engine/quantization envelope, not a general model ranking.

## Data

- Current 8-9B dataset: `results/current/` (curated TSVs + manifest).
- Historical ~4B cohort: `results/v2/final/` and `docs/history/`.

## Limitations

- One GPU, one laptop, one driver version.
- Serving cost, not model quality (accuracy/reasoning).
- Cross-model tokens/s is secondary because tokenizers differ.
- IQ4_XS fits the whole cohort at ctx=4096/parallel=2, but the largest model
  (GLM-4-9B) sits near the VRAM ceiling; any CPU-offload variant would be
  recorded explicitly as such.

## License

No source-code license is asserted for this repository. Model weights are
governed by their own upstream licenses and are not redistributed here.

## Security

Model weights, caches, credentials, raw benchmark cell artifacts, and private
machine paths are excluded (see `.gitignore`). A pre-push gate
(`./scripts/security_check.sh`, also run in CI) checks for secrets, private
paths, oversized files, and non-English text.
