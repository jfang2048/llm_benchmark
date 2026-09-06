# Current benchmark results (mainstream 8-9B cohort)

Curated, machine-readable results for the current primary cohort. Raw AIPerf
artifacts, GPU telemetry and per-request JSONL are git-ignored; only these
summary files are committed.

## Layout

```
results/current/
├── capacity/
│   ├── aggregate.tsv          per (model, concurrency): mean + CI95 over repeats
│   ├── repeats.tsv            every raw repeat cell
│   ├── reliability.tsv        (reliability suite only)
│   ├── manifest.json          engine, image, GPU, serving flags, workload hash
│   └── model_workload.jsonl   the 100-prompt raw-text workload
├── reliability/ ...           same layout, plus reliability.tsv (Wilson 95% CI)
├── shape/ ...                 aggregate + repeats, suite = shape_<profile>
└── llama-bench/               raw engine pp512/tg128 output per model
```

## Suite columns (aggregate.tsv)

`suite, arm, isl, concurrency, pass_runs, unstable_runs, failed_runs,
parsed_runs`, then mean + CI95 for: `error_rate_pct`, `ttft_p50_ms`,
`ttft_p95_ms`, `itl_p50_ms`, `itl_p95_ms`, `latency_p50_ms`, `latency_p95_ms`,
`request_tps`, `output_tps`, `peak_vram_mib`, `peak_power_w`.

## Reliability columns (reliability.tsv)

`arm, concurrency, attempted, successful, failed, success_rate_pct,
wilson_low_pct, wilson_high_pct, error_types` — observed success rate with a
Wilson 95% interval and classified transport error types.

## Status flags

- `PASS` — cell parsed and error rate within the gate.
- `UNSTABLE` — parsed but error rate exceeded the 99.5% reliability gate.
- `FAIL_AIPERF` / `FAIL_PARSE` / `TIMEOUT` — cell did not yield usable results.

`FAILED`/`UNSTABLE` cells are never presented as valid ranking points.

Every manifest records: git commit, image, GPU, serving flags, quantization,
workload SHA256, and per-model GGUF SHA256. Regenerate the dashboard from these
files with `make report-current`.
