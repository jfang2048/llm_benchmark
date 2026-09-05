# Project Backlog

Persistent record of this project's conversion into a reproducible, public
GitHub repository. Kept in-repo as a project log and decision record.

## Goal

Convert the local LLM inference benchmark workspace into a clean, reproducible,
public repository (https://github.com/jfang2048/llm_benchmark): English-only,
no secrets, no model weights, no caches, one-command reproduction, interactive
GitHub Pages report.

## Current State

- Repository published on `main` with a clean, meaningful commit history.
- Validated final experiment (historical run `20260904_192416`) curated under
  `results/final/`.
- Interactive dashboard deployed via GitHub Pages.

## Source Workspace

`$HOME/llm` (generic path; the concrete absolute path is intentionally not
recorded in the public repo).

## Target Repository

https://github.com/jfang2048/llm_benchmark

## Safety Constraints

- PUBLIC repo. Never commit: `.env`, tokens, API keys, private home paths,
  model weights (`*.gguf`), caches (`hf-cache`, `vllm-cache`,
  `torch_compile_cache`), raw Docker inspect dumps, backup files, or logs
  containing secrets.
- Model weights stay local and are git-ignored; they are reproduced via
  `scripts/download_models.sh` with pinned SHA256 verification.
- Benchmark methodology was not silently changed; `scripts/benchmark.sh`
  `final` mode reproduces the historical final experiment.

## Phases (all complete)

- [x] Phase 1  — Inventory
- [x] Phase 2  — Security audit (real secrets found in `.env` and raw
                 Docker inspect files; both excluded and never committed)
- [x] Phase 3  — Repository design / allowlist
- [x] Phase 4  — Reproducible deployment (Docker, compose, scripts)
- [x] Phase 5  — Canonical benchmark runner (`scripts/benchmark.sh`)
- [x] Phase 6  — Results curation (`results/final/` + provenance)
- [x] Phase 7  — Interactive report (`scripts/generate_report.py`, `docs/`)
- [x] Phase 8  — Documentation (README + `docs/*.md`)
- [x] Phase 9  — CI + GitHub Pages workflows
- [x] Phase 10 — Final security review
- [x] Phase 11 — Publish

## Decisions Made

- Curated public dataset = model comparison run `20260904_192416` (final, most
  controlled): Spark-X2.5-4B-Q4_K_M vs Qwen3-4B-Q4_K_M, both llama.cpp.
- Engine cross-benchmark (llama.cpp vs vLLM GGUF/AWQ) kept as documented
  history, not as published data.
- vLLM/Qwen3 deployment + observability stack preserved as reproducible
  secondary configuration.
- Report is regenerated from committed TSV/JSONL data by
  `scripts/generate_report.py`; no displayed number is hand-edited.
- Historical versioned scripts (`cross_benchmark_v*.sh`, `model_benchmark_v*.sh`,
  `prepare_cross_bench*.sh`, `bench_llm.sh`) are excluded and summarized in
  `docs/experiment-history.md`; canonical versions live under `scripts/`.

## Files Explicitly Excluded (never committed, stay local)

- Model weights: `*.gguf` (both 4B models)
- Caches: `hf-cache/`, `vllm-cache/`, `torch_compile_cache/`, `.cache/`
- Secrets: `.env` (real `VLLM_API_KEY`, `GRAFANA_ADMIN_PASSWORD`)
- Raw inventory: `benchmark/inventory/` (Docker inspect dumps + logs)
- Raw historical runs: `benchmark/results*/`, `vllm-qwen3/bench-results/`
- Superseded layout: `spark-x25/`, `vllm-qwen3/`, historical scripts
- Backups: `*.bak`, `*.before-*`

## Current Validation Results

- `bash -n` passes on all `scripts/*.sh`.
- `python3 -m py_compile scripts/generate_report.py` passes.
- All committed JSON files parse.
- `make report` uses `.venv/bin/python` when present (so the Plotly dashboard
  always regenerates), falling back to `python3` otherwise.
- `docker compose config` valid for `configs/llama-cpp.compose.yaml` and
  `configs/observability.compose.yaml` (`vllm.compose.yaml` requires `.env`).
- `./scripts/security_check.sh` passes over the tracked allowlist.

## Current Git State

- Branch `main`, remote `origin` = https://github.com/jfang2048/llm_benchmark.
- Clean history; working tree clean except intentionally ignored local assets.

## Next Action

None — project complete. See README for usage.
