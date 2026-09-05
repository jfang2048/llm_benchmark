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

P0 of Benchmark v2 (reliability diagnosis) in progress — see below.

---

## Benchmark v2

Goal: make the benchmark scientifically trustworthy. The historical run
`20260904_192416` (v1) has substantial `ServerDisconnectedError` rates and is
relabeled as a historical diagnostic, not a final ranking.

- [x] P0 Reliability diagnosis  (root cause + hard gate)
- [x] P1 Benchmark semantics and schema  (results/v2/README.md)
- [x] P2 Capacity benchmark (closed-loop adaptive sweep 1 2 3 4 6 8)
- [x] P3 ISL/OSL workload benchmark (short_chat/balanced/summarization/rag_medium/generation)
- [x] P4 Open-loop / goodput benchmark (25-110% of stable capacity, Poisson, SLO)
- [x] P5 Startup and sustained-load benchmark (process cold start + soak)
- [x] P6 Resource / energy metrics (GPU-side energy estimate)
- [ ] P7 Optional sessions / cache benchmark
- [ ] P8 Optional backend comparison (qwen_llama vs qwen_vllm_gguf)
- [ ] P9 Dashboard v2 (normalized records, SLO/Pareto/heatmap views)
- [ ] P10 Documentation
- [ ] P11 Final validation and publish

### P0 root-cause analysis

`ServerDisconnectedError` is a client-side aiohttp transport error, not a
serving failure. Evidence: every errored request fails at a deterministic
~204 ms (successes ~2015 ms), the container never restarts (docker events show
only `start`), and the llama.cpp server logs zero errors (all accepted requests
complete with `truncated=0`). AIPerf defaults to `--connection-reuse-strategy
pooled`, reusing keep-alive connections that the server closes — the leading
candidate mechanism for the intermittent failure.

Fix (implemented in `scripts/benchmark.sh`): default `CONNECTION_REUSE=never`
(fresh connection per request), plus a hard transport-reliability gate
(`RELIABILITY_MIN_SUCCESS=99.5`); a failed final run is refused unless
`FORCE_UNSTABLE=1`, which marks it `INVALID_FOR_RANKING`.

### P0 diagnostic (confirmed)

c4, 200 requests, same server/seed/workload, only the connection strategy varied:

- pooled (historical default): 8/200 errors = 4.00%
- never (fix):                 0/200 errors = 0.00%

Median latency unaffected (3940 ms pooled vs 3905 ms never). Root cause and fix
confirmed: aiohttp pooled connection reuse racing with the llama.cpp HTTP server
closing keep-alive connections.

## Next Action
P0-P6 complete. Continue P7 (optional sessions/cache benchmark), then P8 backend comparison, P9 dashboard v2, P10 docs, P11 validation+publish.
