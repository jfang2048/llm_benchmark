# Local LLM Inference Benchmark

A reproducible benchmark for local LLM inference on a constrained consumer GPU
(NVIDIA RTX 3060 Laptop, 6 GiB VRAM). It measures **two separate things**:

1. **Serving performance** — token throughput, TTFT, VRAM, and energy under a
   controlled serving policy ([docs/methodology.md](docs/methodology.md)).
2. **Coding / software-engineering capability** — direct coding (EvalPlus,
   LiveCodeBench) and agentic SWE (SWE-bench Verified, DeepSWE, Multilingual,
   Terminal-Bench) with mini-swe-agent
   ([docs/capability-methodology.md](docs/capability-methodology.md)).

The two layers use different serving profiles (parallel 2 vs parallel 1), are
reported separately, and are **never** combined into one synthetic score.

- **Current benchmark — mainstream 8-9B cohort:** four dense open-weight
  8-9B models in IQ4_XS quantization, all served by the same pinned upstream
  llama.cpp build under an identical resource policy and workload.
- **Compact 4B comparison:** Qwen3-4B, Phi-4-mini-instruct, and Gemma 3 4B
  (text-only) in Q4_K_M on the same upstream engine and GPU. The short
  capacity sweep uses a 64-token output cap and a smaller sample.
- **Reference baseline — Spark-X2.5-4B:** a 4B model served on the XHToken
  llama.cpp fork (IQ4_XS). It is shown alongside the cohort as a fixed-hardware
  cross-cohort reference, never as a size-matched competitor.

> **Dashboard:** https://jfang2048.github.io/llm_benchmark/
> **Documentation index:** [docs/README.md](docs/README.md)
> **Capability results:** [docs/capability-results.md](docs/capability-results.md)
> **Problems & solutions:** [docs/capability-troubleshooting.md](docs/capability-troubleshooting.md)
> **Frontier references:** [docs/references.md](docs/references.md)
> **中文文档:** [docs/zh/problems-and-solutions.md](docs/zh/problems-and-solutions.md) · [docs/zh/results-analysis.md](docs/zh/results-analysis.md)

## What this repository does

- Defines a controlled fixed-hardware deployment benchmark
  ([docs/methodology.md](docs/methodology.md)): it measures serving
  performance under one GPU/engine/quantization policy, not model quality.
- Provides two pinned engine profiles (see `configs/models.json`):
  - `upstream_llama_cpp` (`docker/llama-cpp-upstream/`, tag v0.4.0, CUDA arch
    86) for the 8-9B cohort;
  - `xhtoken_llama_cpp` (the Spark-X2.5 XHToken fork) for the reference model.
- Derives the active model set and sweep parameters from a single registry
  (`configs/models.json` + `configs/benchmark.json`); the runner and report
  generator read from it, never from hardcoded model lists.
- Runs the benchmark through a small registry-driven harness (`bench/`) with
  AIPerf as the client.
- Publishes a curated, sanitized dataset under `results/current/` and renders
  a static dashboard from it — every displayed number comes from
  machine-readable `.tsv` files.

## Models

### Current benchmark: mainstream 8-9B cohort

| Model | Parameters | Quantization | License |
|---|---|---|---|
| Qwen3-8B | 8.19B | IQ4_XS | Apache-2.0 |
| DeepSeek-R1-Distill-Llama-8B | 8.03B | IQ4_XS | MIT |
| GLM-4-9B-0414 | 9.40B | IQ4_XS | MIT |
| Yi-1.5-9B-Chat | 8.83B | IQ4_XS | Apache-2.0 |

All four are served as IQ4_XS GGUF artifacts from the same GGUF publisher
(bartowski), each pinned by SHA256 in `configs/models.json`, by the same
pinned upstream `ggml-org/llama.cpp` build. `DeepSeek-R1-Distill-Llama-8B` is
a DeepSeek-distilled Llama-3.1-8B dense model — not the DeepSeek-R1/V3 MoE
architecture.

### Reference baseline: Spark-X2.5-4B

| Model | Parameters | Quantization | Engine |
|---|---|---|---|
| Spark-X2.5-4B | 4.11B | IQ4_XS | XHToken llama.cpp fork |

Spark differs from the cohort in parameter count, serving fork, and
quantization provenance (IQ4_XS quantized locally from the official FP16
GGUF, vs the cohort's Bartowski-published artifacts), so it is reported as a
fixed-hardware reference — not ranked against the 8-9B models. Its engine
profile and commit are pinned in `configs/models.json` exactly like the
upstream build.

See [model selection](docs/model-selection.md#november-2026-model-refresh)
for the November 2026 model refresh and the opt-in smoke commands.

## Test system

| Component | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 3060 Laptop GPU, 6144 MiB VRAM |
| CPU | AMD Ryzen 7 6800H |
| Platform | WSL2, Ubuntu 24.04 |
| Engine (8-9B) | ggml-org/llama.cpp, pinned tag v0.4.0 (CUDA arch 86) |
| Engine (Spark) | XHToken llama.cpp fork, pinned commit |
| Serving policy | `--ctx-size 4096 --parallel 2 --n-gpu-layers 999 --cont-batching` |
| Benchmark tool | NVIDIA AIPerf 0.12.0 |

## Quick start

```bash
git clone https://github.com/jfang2048/llm_benchmark.git
cd llm_benchmark
make setup                 # build both engine images + download/quantize models
make smoke                 # admission gate for both cohorts (serve + smoke + VRAM)
make benchmark             # mainstream 8-9B capacity sweep
make spark                 # Spark reference capacity sweep
make report                # rebuild the current dashboard

# Optional compact 4B comparison after setup
./scripts/download_models.sh qwen3_4b_compact phi4_mini_compact gemma3_4b_compact
make benchmark-compact
```

## Benchmark suites

Run via the registry-driven harness (`bench/runner.py`); `make` targets wrap it.

- `make benchmark` / `make spark` — capacity: closed-loop throughput/latency/
  error sweep vs concurrency (1/2/4/6/8, 60 req/cell, 3 repeats, rotated model
  order).
- `make benchmark-compact` — short sweep at concurrency 1/2/4, 12 requests
  per repeat, two repeats, two warmups, and a 64-token output cap.
- `make reliability` — transport-reliability gate (≥200 requests, Wilson 95%
  CI on success rate, error classification).
- `make shape` — token-controlled ISL/OSL workload sweep.
- `make open-loop` — Poisson load + achieved-throughput sweep.
- `make startup` / `make soak` / `make sessions` — cold-start latency,
  sustained-load thermal degradation, multi-turn latency.
- `make llama-bench` — raw-engine microbenchmark (pp512/tg128) with the same
  upstream binary; kept separate from the AIPerf end-to-end serving numbers.

Serving is gated on a per-model admission test (`scripts/admit.sh`):
healthcheck, a generation request, a 20-request smoke test, and a VRAM/OOM
check before a model enters the benchmark. Capacity results with `FAILED` or
`UNSTABLE` cells are never presented as valid ranking points.

## Results

> **Interactive dashboard:** https://jfang2048.github.io/llm_benchmark/

### Mainstream 8-9B serving results

The IQ4_XS sweep uses 60 measured requests per repeat, three repeats,
and a 128-token output cap. The latency columns show means of each
repeat's p50. The VRAM column shows mean peak usage at concurrency 8.

| Model | TTFT c=1 (ms) | TTFT c=2 (ms) | TTFT c=8 (s) | Output c=2 (tok/s) | Output c=8 (tok/s) | Peak VRAM c=8 (MiB) |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3-8B | 104.1 | 161.9 | 7.60 | 96.3 | 94.5 | 4841 |
| DeepSeek-R1-Distill-Llama-8B | 91.3 | 141.5 | 7.29 | 99.4 | 98.0 | 4725 |
| GLM-4-9B-0414 | 54.6 | 102.5 | 8.50 | 83.3 | 85.4 | 5099 |
| Yi-1.5-9B-Chat | 68.6 | 132.7 | 8.21 | 89.3 | 86.7 | 5043 |

- **Interactive latency.** GLM-4-9B reached the first token in 54.6 ms
  at concurrency 1. DeepSeek delivered the highest output throughput at
  concurrency 2 and used the least VRAM at concurrency 8 in this cohort.
- **Queueing.** Throughput was already close to saturation at concurrency 2.
  At concurrency 8 the first-token median was 7.29–8.50 seconds, with roughly
  the same throughput. The server has two parallel slots.
- **Reliability depends on workload.** Each model completed 200/200 requests
  at concurrency 1 and 4 in the reliability suite. Qwen3-8B and DeepSeek
  had unstable or timed-out cells in the separate 768-input-token workload.

![Output throughput vs concurrency for the mainstream 8–9B models](docs/assets/figures/throughput-vs-concurrency.svg)

### Compact 4B short sweep

The three Q4_K_M models ran on the same upstream llama.cpp build, with
context 4096 and two server slots. Each model completed 72/72 measured
requests across concurrency 1, 2, and 4. TTFT is the mean of the two
per-repeat medians. Peak VRAM is averaged across repeats at concurrency 4.

| Model | TTFT c=1 (ms) | TTFT c=2 (ms) | Output c=2 (tok/s) | Output c=4 (tok/s) | Peak VRAM c=4 (MiB) |
|---|---:|---:|---:|---:|---:|
| Qwen3-4B | 84.8 | 141.6 | 120.3 | 121.5 | 3230 |
| Phi-4-mini-instruct | 42.4 | 83.1 | 128.9 | 127.8 | 3144 |
| Gemma 3 4B (text-only) | 98.5 | 164.3 | 108.2 | 109.6 | 3078 |

Phi-4-mini-instruct had the lowest first-token latency and highest output
throughput at concurrency 2 in this sweep. Gemma used the least VRAM.
At concurrency 4, median TTFT rose to 1.08–1.32 s with throughput within
1.4 tok/s of concurrency 2 for every model. The short sweep used 64 output
tokens per request and 24 measurements per condition. Interpret these values
within the compact cohort. [Full compact results](docs/results.md#compact-4b-short-capacity)

![Output throughput vs concurrency for the compact 4B models](docs/assets/figures/compact-throughput.svg)

### Spark reference and coding capability

Spark-X2.5-4B reached 112.2 tok/s and 186.8 ms median TTFT at concurrency 2,
using about 2847 MiB. At concurrency 8 it held 111.1 tok/s while median TTFT
rose to 7.09 s. This reference uses the XHToken fork and locally quantized
IQ4_XS weights.

![First-token latency vs request throughput for the full sweep](docs/assets/figures/ttft-vs-throughput.svg)

Serving latency and throughput describe speed on this hardware. For
task correctness and coding performance, see [capability results](docs/capability-results.md).
Definitions, exact conditions, and the remaining serving suites are in
[the results guide](docs/results.md).

## Reproduce

```bash
make reproduce              # full: both cohorts + dashboard
REPRODUCE_MODE=smoke make reproduce   # fast admission path
```

## Methodology

See [docs/methodology.md](docs/methodology.md) for metric definitions (TTFT,
ITL, E2E latency, throughput), aggregation, and limitations. This is
a fixed-hardware deployment benchmark: numbers are representative of this
exact GPU/engine/quantization envelope, not a general model ranking.

## Data

- Current 8-9B dataset: `results/current/mainstream-8-9b/`.
- Current Spark reference: `results/current/spark-reference/`.
- Compact short sweep: `results/current/compact-4b/capacity_short/`.
- Historical ~4B cohort: `results/v2/final/` and `docs/history/`.
- Normalized dashboard dataset: `docs/data/current.json` (generated by
  `make report`); the interactive dashboard is `docs/index.html`.

## Limitations

- One GPU, one laptop, one driver version.
- Serving cost, not model quality (accuracy/reasoning).
- Cross-model tokens/s is secondary because tokenizers differ.
- IQ4_XS fits the whole 8-9B cohort at ctx=4096/parallel=2, but the largest
  model (GLM-4-9B) sits near the VRAM ceiling; any CPU-offload variant would
  be recorded explicitly as such.
- Compact results have 24 requests per model and concurrency. The output
  length, quantization, and sample size differ from the full sweeps.
- Spark-X2.5-4B is a reasoning model (emits `reasoning_content`), so its
  output latency reflects reasoning tokens, not only final content.

## License

No source-code license is asserted for this repository. Model weights are
governed by their own upstream licenses and are not redistributed here.

## Security

Model weights, caches, credentials, raw benchmark cell artifacts, and private
machine paths are excluded (see `.gitignore`). A pre-push gate
(`./scripts/security_check.sh`, also run in CI) checks for secrets, private
paths, oversized files, and non-English text.
