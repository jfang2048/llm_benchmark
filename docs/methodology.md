# Benchmark Methodology

## Purpose

This repository benchmarks **local LLM inference** on a constrained consumer
GPU (NVIDIA RTX 3060 Laptop, 6 GiB VRAM). The published experiment answers one
specific question:

> On identical hardware, with an identical serving engine and runtime settings,
> which of two 4B-class models — Spark-X2.5-4B or Qwen3-4B, both in Q4_K_M
> quantization — serves the same workload better in terms of latency,
> throughput, and reliability?

## Experimental design

The published run is a **controlled model comparison**, not a generic
"which model is better" contest. Every variable except the model itself is held
fixed:

| Variable | Value (held fixed) |
|---|---|
| Inference engine | llama.cpp (same binary for both arms) |
| Quantization | Q4_K_M |
| GPU | NVIDIA RTX 3060 Laptop GPU (same device) |
| Context size | 9216 (`--ctx-size 9216`) |
| Parallel slots | 4 (`--parallel 4`) |
| GPU offload | all layers (`--n-gpu-layers 999`) |
| Batching | continuous batching (`--cont-batching`) |
| Workload | identical raw-text prompts, identical order |
| Sampling | `temperature=0`, `ignore_eos=true`, `cache_prompt=false` |
| Output cap | 128 tokens |
| Concurrency | 1, 2, 3, 4 |
| Repeats per cell | 4 |
| Requests per cell | 80 (after 5 warmup) |
| Random seed | 42 |

The single **independent variable** is the model package — checkpoint,
architecture, and tokenizer together. Crossover ordering alternates the two
arms by repeat to reduce temporal/thermal order bias.

## Workload

The workload is 100 synthetic English prompts (20 base cases x 5 textual
variants, tagged `case_id=NNN`). All prompts are SRE/systems/inference-themed
and contain no personal data. The same prompt bytes are sent to both models in
the same order. AIPerf is configured with `cache_prompt=false` on every request
to remove prompt-cache reuse as a confounder.

## Two fairness views

Benchmark v2 measures two distinct things and **never merges them into one
score**:

1. **Semantic workload** — identical user-visible prompt bytes, identical output
   token cap, identical serving settings. This answers: *"which model serves the
   same user workload faster?"* (This is the v1 comparison, retained as
   historical diagnostic.)

2. **Token-controlled workload** — controlled ISL and OSL, so both models process
   an approximately equal *token* workload. This answers: *"how do the models
   behave under approximately equal token workload?"* Implemented by the
   `shape` suite (`./scripts/benchmark.sh shape`). ISL is controlled with the
   Qwen3-4B reference tokenizer and is therefore approximate for Spark-X2.5-4B,
   whose tokenizer differs.

The two views answer different questions and are reported in separate result
files; cross-model tokens/s remains secondary because the tokenizers differ.

## Reliability-gated methodology

The benchmark requires transport success ≥ 99.5% before any performance claim.
The historical run is retained as a diagnostic, not a ranking.

### Reliability gate

Transport success must reach **&ge; 99.5%** before a performance run is
accepted. The historical failure mode was a client-side `aiohttp` transport
error (`ServerDisconnectedError`): AIPerf's default pooled connection reuse
raced with the llama.cpp HTTP server closing keep-alive connections. The fix is
`--connection-reuse-strategy never`. The runner refuses a final publication run
when the gate fails unless `FORCE_UNSTABLE=1`, which marks the run
`INVALID_FOR_RANKING`.

### Measured arm-specific reliability

The Spark-X2.5-4B arm returns `ServerDisconnectedError`/`ConnectionReset` at
input lengths ≥ 256 tokens even with `--connection-reuse-strategy never`,
while Qwen3-4B on the same llama.cpp image and flags is clean through ISL 512.
This is recorded as a measured reliability characteristic of the Spark arm
(see `results/v2/README.md`); the affected shape cells are marked `UNSTABLE` /
`INVALID_FOR_RANKING` and the model ranking rests on the short-prompt `capacity`
suite, where both arms are 100% reliable.

### Terminology

Runs are classified explicitly, and a parsed-but-unstable run is never called
"valid":

- `pass_runs` / `unstable_runs` / `failed_runs` — repeats by outcome.
- `parsed_runs` — repeats whose results were successfully parsed
  (`pass_runs` + `unstable_runs`).
- `attempted_requests` / `successful_requests` / `failed_requests` — request
  counts within a cell.
- Latency metrics are always over **successful requests** and labeled as such.

### Suites

| Suite | Question it answers | Key metrics |
|---|---|---|
| `reliability` | Is transport stable enough to measure? | success rate, error classification |
| `capacity` | What throughput does the model sustain vs concurrency? | request throughput, error rate, latency |
| `shape` | How does the model behave under controlled ISL/OSL? | TTFT/ITL vs token shape |
| `open-loop` | How much Poisson load stays SLO-compliant? | goodput (DistServe definition), SLO compliance |
| `startup` | How long does process cold start take? | container start, model ready, first token |
| `soak` | Does sustained load cause thermal degradation? | GPU temp/power/util, SM clock, throttle flag |
| `sessions` | How does latency grow with conversation context? | TTFT by turn index |
| `backend` | llama.cpp vs vLLM+GGUF on the same GGUF? | engine A/B, kept separate from model ranking |

### Energy metric

`gpu_energy_j` is a **GPU-side energy estimate** (integral of 500 ms
`nvidia-smi` power sampling over the telemetry window, including warmup/idle).
It is not full-system energy and is not MLPerf Power compliant; derived
`gpu_j_per_request` / `gpu_j_per_output_token` carry the same caveat.

### Engine comparison scope

The `backend` suite compares the same Qwen GGUF on llama.cpp vs vLLM+GGUF. It
is an engine A/B only and is never merged into the Spark-vs-Qwen model ranking;
a Qwen-AWQ arm is treated as a quantization/deployment comparison.

## Metric definitions

| Metric | Meaning | Better |
|---|---|---|
| **TTFT** (time to first token) | Latency from request dispatch to the first streamed token. User-perceived startup latency. | lower |
| **ITL** (inter-token latency) | Mean time between consecutive output tokens after generation starts. | lower |
| **E2E latency** | Total time to complete a request (first byte to last token). | lower |
| **Request throughput** | Completed requests per second at a given concurrency. | higher |
| **Output token throughput** | Output tokens generated per second. | higher |
| **Error rate** | Fraction of requests that failed (e.g. `ServerDisconnectedError`). | lower |
| **Peak VRAM** | Maximum GPU memory used during the cell. Efficiency metric, not a quality metric. | lower |
| **Peak power** | Maximum GPU power draw during the cell. Efficiency metric. | lower |

p50/p95 refer to percentiles over the requests in a cell. p95 matters because
tail latency, not the mean, usually defines an inference SLO.

### Why concurrency changes both throughput and latency

Raising concurrency can increase **aggregate** throughput (the GPU stays busy
across requests), but it usually increases **per-request** latency (requests
queue and share compute). The two must be read together with error rate: a
higher-throughput configuration that also fails more requests is not the better
serving result.

### The 6 GiB VRAM constraint

6 GiB of VRAM is a hard deployment constraint. It forces 4-bit quantization,
limits KV-cache capacity, caps maximum context, and bounds the maximum
concurrency before the scheduler runs out of memory. All four concurrency
levels here fit within the constraint, but headroom is small.

## Aggregation

Each cell (arm x concurrency x repeat) yields one AIPerf summary. The published
aggregate reports the **mean and 95% confidence interval** (t-distribution)
across the 4 repeats per (arm, concurrency). With n=4 the CI is wide; the raw
per-repeat values are available in `results/final/results.tsv` and are more
transparent than a pretended tight confidence interval.

## Fairness and limitations

- This is a **deployment/engine-agnostic model comparison**, not an evaluation
  of model *quality* (accuracy, reasoning). It measures serving cost, not
  output correctness.
- **Output token throughput is secondary across models**: Spark-X2.5-4B and
  Qwen3-4B tokenize identical text differently, so cross-model tokens/s is not
  directly comparable. Request-level latency and throughput are the fair basis.
- One GPU, one laptop, one driver version. Results are representative of this
  exact environment, not a general ranking.
- The models have different architectures and vocabularies; "same parameter
  count" (≈4B) does not imply identical compute cost.

See `docs/experiment-history.md` for the earlier engine-comparison (llama.cpp
vs vLLM) work and how this final methodology evolved from it.
