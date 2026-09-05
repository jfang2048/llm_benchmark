# Benchmark

This directory holds the benchmark configuration, workload, and provenance.

- `config.env.example` — template for optional overrides (copy to `config.env`).
- `workloads/model_workload.jsonl` — the committed 100-prompt workload
  (20 base cases x 5 variants, synthetic, English-only). `scripts/benchmark.sh`
  regenerates this deterministically from its embedded 20 base prompts; the
  file here is the canonical committed copy for reference and reproducibility.
- `cross_bench_provenance.txt` — written by `scripts/build.sh` with the exact
  serving image digests (git-ignored as it is machine-generated on build).

## How the benchmark works

The canonical runner is `scripts/benchmark.sh`. It reproduces the validated
final experiment: a **controlled model comparison** between two 4B-class models
served by the **same** llama.cpp binary with the **same** serving flags, the
**same** GPU, the **same** raw prompts in the same order, and the **same**
sampling parameters. The only independent variable is the model package
(checkpoint + architecture + tokenizer).

See `docs/methodology.md` for the full methodology, metric definitions, and
fairness limitations.

## Modes

```bash
MODE=smoke ./scripts/benchmark.sh   # fast pipeline validation (8 req, 1 warmup, 1 repeat)
MODE=final ./scripts/benchmark.sh   # full matrix (80 req, 5 warmup, 4 repeats, C=1..4)
```

Results land in `results/runs/YYYYMMDD_HHMMSS/` (git-ignored). A run produces
`results.tsv`, `aggregate.tsv`, `error_details.tsv`, `runtime_config.txt`,
`model_comparison.md`, `summary.txt`, `workload.jsonl`, and per-cell raw
artifacts (AIPerf records, GPU telemetry, server logs).
