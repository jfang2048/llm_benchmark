# Benchmark selection

Why each coding / software-engineering benchmark is used, what it measures,
and — critically — what a local subset result does and does not mean.

## Two classes

- **Direct coding** — the model alone completes a programming task from a
  prompt. No agent scaffold, no tools, no repo context.
- **Agentic software engineering** — the model + a fixed agent harness
  (mini-swe-agent) + a context policy + tool interaction, working inside a
  repository. These scores are **not** pure model intelligence.

The two are reported separately and are never averaged into one score.

## Direct coding

### EvalPlus (HumanEval+ / MBPP+)

- Repo: `evalplus/evalplus`, pinned `v0.3.1` (`26d6d00`).
- Measures: basic function-completion correctness.
- Tasks: HumanEval 164, MBPP 378; `+` variants add ~80× more tests to catch
  fragile solutions.
- Contamination: **not** resistant. These are old, widely-memorized datasets.
  Treat as a floor check, not a measure of generalization.
- Protocol: `temperature=0, n=1`, reasoning off, official executor.
- Reported: HumanEval / HumanEval+ / MBPP / MBPP+ pass@1, plus the
  **base → plus drop** (fragile solutions that only pass weak tests).

### LiveCodeBench

- Repo: `LiveCodeBench/LiveCodeBench`, pinned `main` (`28fef95`).
- Measures: competitive-programming code generation on recent problems
  (contamination-resistant because problems are newer).
- Protocol: `LOCAL PROTOCOL` — lite code-generation path, `n=1`. This is
  **not** leaderboard-equivalent (the official protocol samples `n≥20` and
  estimates pass@k).
- Reported: pass@1 by scenario; problem publication dates recorded when
  available.

## Agentic software engineering

All use **one pinned mini-swe-agent** (`SWE-agent/mini-swe-agent` @ `04d809c`)
with a bash/text action interface (no model-specific function calling), the
same prompt/config/action format across models, and the official per-benchmark
evaluator. `max_workers=1`.

### SWE-bench Verified

- Repo: `SWE-bench/SWE-bench`, pinned `main` (`02e7a74`).
- Measures: resolving real GitHub issues in real repositories.
- Tasks: 500 verified instances.
- Local subset: **SWE-bench Verified Local-20** (seed 42, stratified by repo).
  This is **not** the official full 500-task score.

### DeepSWE v1.1

- Repo: `datacurve-ai/deep-swe` @ `0b9fabb`; harness `datacurve-ai/pier` @
  `0c802fc` (Harbor fork).
- Measures: original long-horizon engineering tasks (not isolated bug fixes).
- Tasks: ~113 across Python, TypeScript, JavaScript, Go, Rust.
- Local subset: **DeepSWE Local-10** (seed 42, stratified by language/repo/
  reference-patch size). Not leaderboard-equivalent.

### SWE-bench Multilingual

- Repo: `SWE-bench/swe-bench-multilingual-tasks` @ `6e08cbc`.
- Measures: repo-level tasks across 9 languages.
- Tasks: 300.
- Local subset: **SWE-Multilingual Local-18** (2 per language, seed 42),
  expandable to Local-45 (5 per language).

### Terminal-Bench 2.0

- Repo: `harbor-framework/terminal-bench-2` @ `2fd12b8`; framework
  `harbor-framework/harbor` @ `90e28af`.
- Measures: terminal/agent work (Linux, CLI, build/debugging, systems).
- Local subset: **Terminal-Bench Local-10** (seed 42, stratified by category).

### Frontier pilots

- **SWE-bench Pro** (`scaleapi/SWE-bench_Pro-os` @ `ca10a60`): 731 public
  instances, far harder than Verified. Pilot: **Local-10**.
- **SWE-EVO** (`SWE-EVO/SWE-EVO` @ `9b83d5a`): long-horizon software
  evolution. Pilot: **Local-4** (very small, extremely difficult).

Frontier pilots are diagnostics, not full runs — running all 731 Pro or the
full SWE-EVO set on this laptop is not tractable.

## Not applicable

- **SWE-bench Multimodal v2** — `NOT_APPLICABLE_NO_VISION` (models are
  text-only; screenshots are not OCR-converted and relabeled).
- **SWE-smith** — training-data/environment infrastructure, not an evaluation
  score.
- **DeepSWE-Preview** — this is a ~32B RL-trained model (Qwen3-32B based),
  NOT the Datacurve DeepSWE benchmark. Not deployed here (6 GiB VRAM).

## Terminology

- `resolved %` / `pass %` always reported with `n` and Wilson 95% CI. Never
  "100%" without `n`.
- Infrastructure failures (OOM, verifier errors, environment errors) are kept
  separate from model/agent failures.
- `achieved request throughput` / `transport success rate` are transport-level
  metrics; no SLO goodput is fabricated.
