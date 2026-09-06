# Benchmark Methodology

## Purpose

This repository benchmarks **local LLM inference serving** on a constrained
consumer GPU (NVIDIA RTX 3060 Laptop, 6 GiB VRAM). The current experiment
answers one specific question:

> On identical hardware, with an identical pinned serving engine, quantization
> and runtime settings, which of four mainstream 8-9B dense models — served in
> IQ4_XS — sustains the same workload better in terms of latency, throughput,
> reliability and resource use?

This is a **fixed-hardware deployment benchmark**, not a pure architecture
comparison and not an evaluation of model quality.

## Experimental design

The run is a **controlled model comparison**. Every variable except the model
itself is held fixed:

| Variable | Value (held fixed) |
|---|---|
| Inference engine | ggml-org/llama.cpp, pinned tag v0.4.0 (same binary for all models) |
| Quantization | IQ4_XS |
| GPU | NVIDIA RTX 3060 Laptop GPU (same device) |
| Context size | 4096 (`--ctx-size 4096`) |
| Parallel slots | 2 (`--parallel 2`) |
| GPU offload | all layers (`--n-gpu-layers 999`) |
| Batching | continuous batching (`--cont-batching`) |
| Workload | identical raw-text prompts, identical order |
| Sampling | `temperature=0`, `ignore_eos=true`, `cache_prompt=false` |
| Output cap | 128 tokens |
| Concurrency | 1, 2, 4, 6, 8 |
| Repeats per cell | 3 |
| Requests per cell | 60 (after 5 warmup) |
| Random seed | 42 |

The single **independent variable** is the model package — checkpoint,
architecture, and tokenizer together. Model order is rotated between repeats
to reduce temporal/thermal order bias.

## Workload

The workload is 100 synthetic English prompts (20 base cases x 5 textual
variants, tagged `case_id=NNN`). All prompts are SRE/systems/inference-themed
and contain no personal data. The same prompt bytes are sent to every model in
the same order. AIPerf is configured with `cache_prompt=false` on every request
to remove prompt-cache reuse as a confounder.

## Two fairness views

Two distinct workloads are measured and **never merged into one score**:

1. **Semantic workload** — identical user-visible prompt bytes, identical output
   token cap, identical serving settings. Answers: *"which model serves the
   same user workload faster?"* (capacity, reliability, soak).

2. **Token-controlled workload** — controlled ISL and OSL, using **each model's
   own tokenizer** so the input length reflects that model's actual token
   count. Answers: *"how does each model behave at a given token shape?"*
   (shape suite).

The two views answer different questions and are reported in separate result
files; cross-model tokens/s remains secondary because the tokenizers differ.

## Reliability-gated methodology

The benchmark requires transport success **&ge; 99.5%** before any performance
cell is accepted as a ranking point.

### Reliability gate

AIPerf's default pooled connection reuse raced with the llama.cpp HTTP server
closing keep-alive connections, so every request uses
`--connection-reuse-strategy never`. A parsed-but-unstable cell is marked
`UNSTABLE` and is never presented as valid. The reliability suite reports, per
model and concurrency: attempted / successful / failed requests, observed
success rate, a Wilson 95% confidence interval, and the classified error types.

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
| `reliability` | Is transport stable enough to measure? | success rate, Wilson CI, error classification |
| `capacity` | What throughput does the model sustain vs concurrency? | request throughput, error rate, latency |
| `shape` | How does the model behave under controlled ISL/OSL? | TTFT/ITL vs token shape |
| `open-loop` | How much Poisson load stays SLO-compliant? | goodput, SLO compliance |
| `startup` | How long does process cold start take? | container start, model ready, first token |
| `soak` | Does sustained load cause thermal degradation? | GPU temp/power/util, SM clock |
| `sessions` | How does latency grow with conversation context? | TTFT by turn index |
| `llama-bench` | Raw engine token throughput? | pp512 / tg128 tokens/s (kept separate from AIPerf serving numbers) |

### Energy metric

`gpu_energy_j` is a **GPU-side energy estimate** (integral of 500 ms
`nvidia-smi` power sampling over the telemetry window, including warmup/idle).
It is not full-system energy and is not MLPerf Power compliant; derived
`gpu_j_per_request` / `gpu_j_per_output_token` carry the same caveat.

## Metric definitions

| Metric | Meaning | Better |
|---|---|---|
| **TTFT** (time to first token) | Latency from request dispatch to the first streamed token. | lower |
| **ITL** (inter-token latency) | Mean time between consecutive output tokens. | lower |
| **E2E latency** | Total time to complete a request. | lower |
| **Request throughput** | Completed requests per second at a given concurrency. | higher |
| **Output token throughput** | Output tokens generated per second. | higher |
| **Error rate** | Fraction of requests that failed. | lower |
| **Peak VRAM** | Maximum GPU memory used during the cell. Efficiency, not quality. | lower |
| **Peak power** | Maximum GPU power draw during the cell. Efficiency. | lower |

p50/p95 refer to percentiles over the requests in a cell. p95 matters because
tail latency, not the mean, usually defines an inference SLO.

### Why concurrency changes both throughput and latency

Raising concurrency can increase **aggregate** throughput (the GPU stays busy),
but it usually increases **per-request** latency (requests queue and share
compute). The two must be read together with error rate: a higher-throughput
configuration that also fails more requests is not the better serving result.

### The 6 GiB VRAM constraint

6 GiB of VRAM is a hard deployment constraint. It forces IQ4_XS quantization
and a 4096-token serving context, and it bounds the maximum concurrency before
the scheduler runs out of memory. Admission tests confirmed all four models fit
without CPU offload at this policy (peak 5.1 GiB for GLM-4-9B); any CPU-offload
variant would be recorded explicitly.

## Aggregation

Each cell (model x concurrency x repeat) yields one AIPerf summary. The
aggregate reports the **mean and 95% confidence interval** (t-distribution)
across the 3 repeats per (model, concurrency). The raw per-repeat values are
published alongside the aggregate (`repeats.tsv`) and are more transparent than
a pretended tight confidence interval.

## Fairness and limitations

- This is a **deployment benchmark**, not an evaluation of model *quality*
  (accuracy, reasoning). It measures serving cost, not output correctness.
- **Output token throughput is secondary across models**: the four models
  tokenize identical text differently, so cross-model tokens/s is not directly
  comparable. Request-level latency and throughput are the fair basis.
- One GPU, one laptop, one driver version. Results are representative of this
  exact environment, not a general ranking.
- The models have different architectures and vocabularies; a similar parameter
  count does not imply identical compute cost.

See `docs/experiment-history.md` for the earlier 4B cohort and the engine
comparison work this methodology evolved from.
