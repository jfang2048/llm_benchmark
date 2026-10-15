# Capability evaluation — problems and solutions

A retrospective of the coding / software-engineering capability layer: the
design/correctness problems that were identified up front, the implementation
problems that surfaced while building it, and the fix applied to each. This is
a record, not a how-to.

## Part 1 — Design and correctness problems (from the audit)

These were identified before (or during) the build and are now fixed.

### P0 — SWE-bench report parsing was wrong

The first draft read `report["f2p"]` / `report["p2p"]`. The pinned official
SWE-bench `get_eval_report` writes a different structure:

```json
{ "resolved": false, "patch_exists": true, "patch_successfully_applied": true,
  "patch_is_None": false, "infra_failure": false,
  "tests_status": { "FAIL_TO_PASS": {"success": [], "failure": []},
                    "PASS_TO_PASS": {"success": [], "failure": []} } }
```

Fix: `evals/swe.py` now parses the real fields and `classify_report()` maps
each instance to `RESOLVED / NO_PATCH / PATCH_INVALID / TEST_FAILURE /
ENVIRONMENT_ERROR / MISSING_REPORT`. Infrastructure failures are reported
separately and never silently counted as model failures. Summary reports
`resolved / validly_evaluated_tasks`, plus `infrastructure_failures` and
`coverage`, so the denominator of every percentage is explicit.

### P1 — Manifest overwrote provenance

One `manifest.json` per benchmark was overwritten on each model run, losing the
earlier model's provenance.

Fix: `normalize.write_manifest` now appends to a multi-run manifest
(`benchmark_metadata` + `runs[]`), keyed by a deterministic protocol
fingerprint (benchmark commit, model SHA256, engine commit, agent commit,
context, generation settings). A later model never clobbers an earlier one.

### P2 — Manifest semantics conflated the two suites

The manifest copied the same protocol metadata for direct coding and agentic
SWE.

Fix: `make_manifest(kind=...)` records real per-kind values. `kind="direct"`
records `serving_profile=direct_coding_profile`, `agent="none"`, the direct-code
generation settings, and a prompt-protocol note. `kind="agent"` records
`serving_profile=agent_profile`, the agent name/commit, max iterations, context,
and generation settings.

### P3 — Environment was not reproducible

The capability code hardcoded `~/venvs/aiperf` and `~/venvs/eval`.

Fix: one project-owned `.venv-eval/` (git-ignored) with a tracked
`requirements-eval.txt`. `scripts/eval_setup.sh` builds it and installs
mini-swe-agent + swebench from the pinned git clones in `.cache/evals/` (exact
commits, not mutable PyPI releases). The Makefile derives
`EVALPY=.venv-eval/bin/python`. No `~/venvs/*` path remains in tracked code.

### P4 — Public Make targets were placeholders

Several `eval-*` targets only echoed a benchmark name.

Fix: every target now executes a real adapter (see Part 3). Targets that are
genuinely deferred (SWE-bench Pro, SWE-EVO) say so explicitly instead of
echoing. `make help` has a Capability section; `eval-standard` runs only the
feasible local suite.

### P5 — Admission could be aborted by one model

One ineligible model would have stopped the loop.

Fix: `eval-admit` runs context + agent admission for every model independently
and continues on failure. Eligibility (`ELIGIBLE / CONTEXT_INELIGIBLE /
TRANSPORT_INELIGIBLE / OOM / ERROR`) is measured, not assumed.

### P6 — EvalPlus wording

The generator built its own chat prompt. It must not be claimed as "official
prompt".

Fix: results are described as "local chat generation protocol + official
EvalPlus executor" (temperature 0, n=1, reasoning off). The base → plus drop is
reported to flag solutions that only pass weak tests.

### P7 — LiveCodeBench

Uses a `LOCAL PROTOCOL` (n=1) against the local endpoint, explicitly not
leaderboard-equivalent; the release is recorded per run.

### P8–P11 — Direct coding / SWE scope

- EvalPlus completed for all 5 models (HumanEval / HumanEval+ / MBPP / MBPP+).
- SWE-bench Verified Local-20, DeepSWE Local-10, SWE-Multilingual Local-18,
  Terminal-Bench Local-10, SWE-bench-Live Local-10 subsets are committed
  (seed 42, stratified, task-IDs hash in each file).
- DeepSWE/Multilingual/Terminal/Live have real adapters (official pier / harbor
  / swebench harness + mini-swe-agent; no custom judge).

### P12 — Frontier selection for 2026

- Added SWE-bench-Live (contamination-resistant current signal), Senior
  SWE-Bench (pilot), ProgramBench (pilot).
- SWE-bench Pro is `DEFERRED` (task-quality review); SWE-EVO / SWE-rebench
  deferred.

### P13–P15 — Security, CI, Pages

- SWE/DeepSWE/Harbor task containers are treated as untrusted: no `$HOME`, SSH
  keys, credentials, `.env`, or Docker socket; network restricted where the
  benchmark permits; only the host orchestrator controls Docker.
- CI now compiles `evals/*.py`, runs `tests/test_capability.py` (Wilson,
  merge/upsert, multi-run manifest, fingerprint, report parser, infra-failure
  handling), regenerates `capability.json`, and validates eval JSON.
- Pages listens to `results/capability/**`, `evals/**`, `scripts/eval_report.py`
  and regenerates `capability.json` before the dashboard.

### P16–P17 — Dashboard and docs

- Capability half of the dashboard is separate from serving (top-level nav
  split): overview matrix, direct coding, per-benchmark resolved rate with
  Wilson CI, failure taxonomy, task explorer. No combined score; Spark stays
  `REFERENCE / 4B`.
- Docs: `capability-methodology.md`, `capability-results.md`,
  `benchmark-selection.md` — each local subset is labeled not
  leaderboard-equivalent.

## Part 2 — Implementation problems encountered and fixed

In roughly the order they surfaced.

1. **llama.cpp server hung under sustained load.** The `--reasoning-format
   deepseek` flag (added to route thinking tokens) caused the v0.4.0 server to
   stop answering after ~100 requests. Fix: drop that flag, keep
   `--reasoning off`, add a 180 s per-request timeout and a restart-on-hang
   retry.

2. **EvalPlus v0.3.1 result format.** The evaluator writes
   `eval[tid] = [{base_status, plus_status, ...}]`, not the assumed
   base/plus bool lists. Fix: `parse_eval` reads `base_status`/`plus_status`.

3. **Model arm vs id mismatch.** 4 of 5 models have a short `arm` differing
   from their full `id` (e.g. `deepseek_r1_8b` vs `deepseek_r1_distill_llama_8b`);
   only `qwen3_8b` matched. Fix: `model_by_arm` matches both; the eval scripts
   use the canonical short arms.

4. **summary.tsv / tasks.tsv overwrite.** Each dataset run clobbered the other.
   Fix: `_merge_rows` upserts by key columns (e.g. `model+dataset`,
   `task_id+model`).

5. **security_check flagged `/home/jfang`** in a docstring example. Fix:
   replace with `$HOME`.

6. **XHToken (Spark) fork hangs on some prompts.** The Spark fork intermittently
   stops decoding on certain inputs. Fix: the restart-on-hang retry + resume
   (samples are cached per task, so a resume skips completed work).

7. **DeepSeek-R1-Distill degenerates under reasoning-off.** With `--reasoning
   off`, the R1-distill model frequently emits `"\nWait,"` and other truncated
   reasoning fragments, so its EvalPlus numbers (HumanEval 20.1%, MBPP 31.2%)
   are a lower bound, not representative of its reasoning-native capability.
   This is documented in the results, not hidden.

8. **mini-swe-agent first-time setup hang.** `mini` ran its interactive setup
   prompt on first use and blocked (no TTY). Fix: set `MSWEA_CONFIGURED=true`
   and `OPENAI_API_KEY=sk-local` in the subprocess env.

9. **litellm cost-tracking error.** The local model name isn't in litellm's
   price map, so cost calculation raised `RuntimeError`. Fix:
   `MSWEA_COST_TRACKING=ignore_errors`.

10. **Trajectory step count was 0.** The trajectory JSON uses `messages`, not
    `trajectory`/`steps`. Fix: parse `messages`; admission is now
    `harness_connected AND produced >= 1 bash action`, with task `resolved`
    recorded separately as a capability signal rather than a harness gate.

11. **Docker image pull exceeded mini-swe-agent's 120 s `docker run` timeout.**
    SWE-bench images are 10+ GB. Fix: pre-pull the image before running.

12. **Context overflow.** The SWE problem statement + template is ~9.7K tokens,
    overflowing `--ctx-size 8192` (`ContextWindowExceededError`). Fix: raise
    the agent context to 16384 — the max the 8-9B IQ4_XS models serve on 6 GiB
    VRAM (measured by context admission).

13. **Stale empty patch caused a resume skip.** A failed first run wrote an
    empty patch, and the next run skipped the instance as "already done". Fix:
    delete stale predictions before re-running.

14. **`.venv-eval/` was briefly staged.** `git add -A` picked up the venv before
    `.gitignore` covered it. Fix: added `.venv-eval/` and reset.

15. **`eval_setup.sh` had `VPY` instead of `"$VPY"`**, which bash read as a
    command name (`command not found`). Fix: quote the variable.

16. **tmux sessions died across context rebuilds.** Long GPU jobs restarted from
    the sample cache each time. Fix: run long jobs in tmux with resume-capable
    scripts; check for existing jobs before starting new ones (no duplicates).

17. **HF dataset name for SWE-bench-Live.** `microsoft/SWE-bench-Live` does not
    exist on the Hub; the dataset is `SWE-bench-Live/SWE-bench-Live` with a
    frozen `verified` split. Fix: use the correct dataset + split in `live.py`.

18. **SWE-bench Multilingual has no `language` field.** The language is not in
    the dataset columns; it is derived from the repository's primary language
    (verified per-repo via GitHub, matching the paper's 9-language counts).

19. **Admission schema collision.** Context and agent admission wrote different
    column sets to the same `admission/tasks.tsv`. Fix: separate benches
    (`admission` for context, `admission-agent` for harness) with explicit
    key columns.

## Part 3 — Current state

- **EvalPlus complete for all 5 models** (HumanEval / HumanEval+ / MBPP /
  MBPP+), official executor, temperature 0, n=1, reasoning off.
- **Context admission**: qwen3_8b / deepseek_r1_8b / glm4_9b / spark_llama
  `ELIGIBLE` at 16384; yi_15_9b `TRANSPORT_INELIGIBLE` (native ~4K).
- **Agent admission** (reasoning off): harness connects for all models; Spark
  resolves the tiny task; the 8-9B models produce few actions — confirming that
  reasoning-off limits agentic capability, which is why the SWE sweeps use
  `--reasoning auto`.
- **SWE Verified one-task validation** in progress (qwen3_8b, astropy,
  ctx 16384, reasoning auto).
- Agentic reasoning policy: **direct coding = reasoning off** (uniform local
  protocol); **agentic SWE = reasoning auto** (natural mode).
