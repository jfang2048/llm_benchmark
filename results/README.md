# Results

## Curated public dataset

`results/final/` is the deliberately curated, sanitized public dataset. It
contains only the validated final experiment (historical run `20260904_192416`),
a controlled comparison of **Spark-X2.5-4B-Q4_K_M vs Qwen3-4B-Q4_K_M on llama.cpp**.

| File | Description |
|---|---|
| `results.tsv` | Per-cell raw results (2 models x 4 concurrency levels x 4 repeats + sanity cells) |
| `aggregate.tsv` | Mean and 95% CI per arm/concurrency |
| `error_summary.tsv` | Classified request errors per cell |
| `runtime_config.txt` | Serving-control equivalence report (same image + same flags) |
| `workload.jsonl` | The 100-prompt workload (20 base x 5 variants) |
| `workload.sha256` | SHA256 of the workload (path-normalized) |
| `model_comparison.md` | Generated side-by-side comparison tables |
| `summary.md` | Generated concise summary |
| `provenance.json` | Machine-readable provenance (models, software, hardware, hashes) |

`model_comparison.md`, `summary.md`, and `provenance.json` are regenerated from
the committed `.tsv`/`.jsonl` files by `scripts/generate_report.py` — never
hand-edited. Run `make report` to rebuild them.

## Local run output

New benchmark runs write to `results/runs/YYYYMMDD_HHMMSS/`. This directory is
git-ignored: you choose which run (if any) becomes the public baseline. The
raw per-cell artifacts (AIPerf request records, GPU telemetry, server logs)
are large and machine-specific, so they stay local.

## Why only one run is published

The workspace contained many historical run directories (early A/B tests,
engine cross-benchmarks, methodology experiments, and diagnostic iterations).
Only the final, most controlled model-comparison run is published; the rest is
summarized in `docs/experiment-history.md`.
