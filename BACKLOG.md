# Project Backlog

## Goal
Convert /home/jfang/llm (local LLM inference benchmark workspace) into a clean,
reproducible, public GitHub repo at https://github.com/jfang2048/llm_benchmark
(branch main). English-only, no secrets, no model weights, no caches, one-command
reproducibility, interactive GitHub Pages report.

## Current State
- Source: /home/jfang/llm — already `git init`-ed, branch `master`, NO commits, NO remote.
- gh CLI authenticated as jfang2048 (installed at ~/.local/bin/gh).
- Target repo jfang2048/llm_benchmark is public, empty, default branch `main`.

## Source Workspace
/home/jfang/llm

## Target Repository
https://github.com/jfang2048/llm_benchmark

## Safety Constraints
- PUBLIC repo. Never commit: .env, tokens, API keys, /home/jfang paths, model weights
  (*.gguf), caches (hf-cache, vllm-cache, torch_compile_cache), raw docker inspect
  dumps, *.bak, *.log with secrets, machine identifiers.
- Model weights stay local & ignored. Reproduce via download + SHA256.
- Do not change benchmark methodology silently. `final` mode must reproduce run 20260904_192416.

## Phase 1 - Inventory
- [x] Enumerate tree, sizes, git state (branch master, no commits, no remote)
- [x] Read existing README.md, .gitignore
- [x] Identify final benchmark: results-model/20260904_192416 (model benchmark v11)
- [x] Identify engine cross-benchmark history: results-cross/*, results/*, bench-results/*
- [x] Capture environment (nvidia-smi, docker, lscpu, python)

## Phase 2 - Security Audit
- [x] .env has real secrets: VLLM_API_KEY (64 chars), GRAFANA_ADMIN_PASSWORD (32) -> excluded
- [x] docker inspect JSONs contain "Env" arrays (may hold API key) -> excluded
- [x] /home/jfang appears in result artifacts -> sanitize curated copies
- [ ] Build scripts/security_check.sh and run it as final gate

## Phase 3 - Repository Design
- [x] Design allowlist (see Files Explicitly Excluded)
- [x] Canonical script set decided (scripts/*.sh + generate_report.py)

## Phase 4 - Reproducible Deployment
- [ ] docker/llama-cpp/Dockerfile (from spark-x25/Dockerfile)
- [ ] docker/vllm-gguf/Dockerfile (from benchmark/Dockerfile.vllm-gguf)
- [ ] configs/ compose files (llama + vllm + observability)
- [ ] scripts/preflight.sh, build.sh, deploy.sh, healthcheck.sh, download_models.sh

## Phase 5 - Benchmark Reproduction
- [ ] scripts/benchmark.sh (from model_benchmark_v11_diag.sh; MODE=final|smoke)
- [ ] scripts/reproduce.sh (one-command)
- [ ] scripts/cleanup.sh

## Phase 6 - Results Curation
- [x] Confirm clean data: results.tsv, aggregate.tsv, error_details.tsv, workload.jsonl (100 prompts), runtime_config.txt
- [ ] results/final/ curated copy (sanitized), provenance.json, README

## Phase 7 - Interactive Report
- [ ] scripts/generate_report.py (regenerate model_comparison.md + summary.md + provenance.json + docs/index.html + docs/assets SVGs)

## Phase 8 - Documentation
- [ ] README.md, docs/methodology.md, environment.md, architecture.md, troubleshooting.md, experiment-history.md, models/README.md, benchmark/README.md, results/README.md

## Phase 9 - CI / GitHub Pages
- [ ] .github/workflows/ci.yml, pages.yml
- [ ] requirements-report.txt

## Phase 10 - Final Security Review
- [ ] ./scripts/security_check.sh, CJK scan, git ls-files allowlist, size audit

## Phase 11 - Publish
- [ ] git init -b main (rename from master), add remote, commit history, push
- [ ] Verify remote tree, enable Pages, verify URL

## Decisions Made
- Curated public dataset = model comparison run 20260904_192416 (final, most controlled).
- Engine cross-benchmark (llama.cpp vs vLLM GGUF/AWQ) kept as historical documentation only.
- Primary deliverable model comparison: Spark-X2.5-4B-Q4_K_M vs Qwen3-4B-Q4_K_M, both llama.cpp.
- vLLM/Qwen3 deployment + observability stack preserved as reproducible secondary config.
- Report regenerated from committed TSV data by scripts/generate_report.py (no hand-edited numbers).

## Files Explicitly Excluded (never committed, stay local)
- *.gguf (both models), hf-cache/, vllm-cache/, torch_compile_cache/
- .env (real secrets), all *.bak, compose.*.bak, .before-host-metrics
- benchmark/inventory/ (raw docker inspect + logs)
- benchmark/results*/** raw historical run dirs (curated subset copied to results/final/)
- vllm-qwen3/bench-results/** raw AIPerf JSON
- *.log, .cross_benchmark.lock, .cross_benchmark.pid

## Current Validation Results
- (none yet)

## Current Git State
- branch master, no commits, no remote. Will rename to main + set origin.

## Next Action
Write .gitignore/.gitattributes/.env.example/Makefile, then scripts/ and docker/.
