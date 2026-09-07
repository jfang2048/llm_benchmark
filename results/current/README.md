# Current results

Curated, sanitized benchmark results for the current cohorts. Raw AIPerf
artifacts, GPU telemetry, per-request JSONL, and server logs are git-ignored;
only the summary TSVs and manifests below are committed.

```
results/current/
  mainstream-8-9b/    # primary 8-9B cohort (IQ4_XS, upstream llama.cpp)
  spark-reference/    # Spark-X2.5-4B reference (IQ4_XS, XHToken fork)
```

Each suite directory contains:

- `aggregate.tsv` — mean + 95% CI across repeats per (model, condition).
- `repeats.tsv` — every raw repeat point (the source of the aggregate).
- `manifest.json` — environment provenance: engine/image/commit, serving
  flags, quantization, GPU, driver/CUDA, AIPerf version, workload hash, run ID,
  git commit.
- `model_workload.jsonl` — the exact prompt bytes used (identical across models).

The Spark reference is a fixed-hardware cross-cohort baseline (different
parameter count, engine fork, and quantization); it is reported alongside the
8-9B cohort but never ranked against it.
