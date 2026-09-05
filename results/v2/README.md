# Benchmark v2 Results

Benchmark v2 separates its results from the historical v1 dataset
(`results/final/`). v2 runs land under `results/v2/runs/<RUN_ID>/` and are
git-ignored; a validated, sanitized final v2 run is promoted to
`results/v2/final/` (to be created once the reliability gate passes).

## Schema

Every v2 run directory contains:

### manifest.json
Machine-readable provenance — required for a run to be scientifically reusable:

```json
{
  "run_id": "YYYYMMDD_HHMMSS",
  "mode": "capacity|shape|open-loop|startup|soak|sessions|final",
  "git_commit": "<sha>",
  "models": ["Spark-X2.5-4B-Q4_K_M", "Qwen3-4B-Q4_K_M"],
  "model_sha256": { "<file>": "<sha256>" },
  "llama_cpp_image_id": "sha256:...",
  "aiperf_version": "0.12.0",
  "gpu": "NVIDIA GeForce RTX 3060 Laptop GPU",
  "driver": "610.74",
  "cuda": "13.3",
  "serving_flags": ["--ctx-size","9216","--parallel","4","..."],
  "workload_sha256": "<sha256>",
  "config": { "connection_reuse": "never", "temperature": 0, "ignore_eos": true, ... },
  "generated_at": "<iso8601>"
}
```

### repeats.tsv
One row per benchmark cell (arm x concurrency x repeat). Columns:

```
arm  suite  isl  concurrency  repeat  status  error_rate_pct
attempted_requests  successful_requests  failed_requests  success_rate_pct
input_tokens_avg  output_tokens_avg
ttft_avg_ms  ttft_p50_ms  ttft_p95_ms  ttft_p99_ms
itl_avg_ms  itl_p50_ms  itl_p95_ms  itl_p99_ms
latency_avg_ms  latency_p50_ms  latency_p95_ms  latency_p99_ms
request_tps  output_tps
peak_vram_mib  peak_power_w  avg_gpu_util_pct  peak_temp_c
```

`status` is one of `PASS`, `UNSTABLE`, `TIMEOUT`, `FAIL_AIPERF`, `FAIL_PARSE`.
`UNSTABLE` is **not** a pass and is never presented as such. All latency/throughput
metrics are computed over **successful** requests only.

### aggregate.tsv
Mean and 95% CI (t-distribution) per (arm, concurrency), with explicit
`pass_runs`, `unstable_runs`, `failed_runs`, `parsed_runs` counts. Error/success
proportions use a Wilson binomial interval, not a t-interval over percentages.

### errors.tsv
Classified request errors per cell (type, count, sample message).

### resource_summary.tsv
Per-cell GPU resource aggregates: average/p95 utilization, peak VRAM, average/peak
power, peak temperature, and (when sampled) a GPU-side energy estimate
(`gpu_energy_j` = integral of sampled power over time).

### slo_summary.tsv
Per (model, load fraction, SLO profile): `attempted`, `slo_compliant`,
`good_request_fraction`, and `goodput_req_s` (SLO-compliant requests per second).
Goodput follows the DistServe definition: successful requests satisfying ALL
configured SLOs; errored requests count as non-compliant. Two reference SLO
profiles are reported — `interactive` (TTFT <= 500 ms, TPOT <= 30 ms) and
`server` (TTFT <= 2000 ms, TPOT <= 100 ms) — inspired by contemporary MLPerf LLM
serving scenarios, but this repository is **not** claiming MLPerf compliance.
The max SLO-compliant request rate is derived as the highest load point whose
`good_request_fraction` remains at or near 1.0.

### workload_manifest.json
Describes the workload used (prompt count, hash, ISL/OSL profile, sampling).

## Terminology

- `attempted_requests` — every request AIPerf dispatched in a cell.
- `successful_requests` — requests that completed without a transport/API error.
- `failed_requests` — requests with a transport/API error (count against goodput).
- `parsed_runs` — repeats whose results were successfully parsed (PASS + UNSTABLE).
- Latency metrics are always over successful requests and labeled accordingly.
