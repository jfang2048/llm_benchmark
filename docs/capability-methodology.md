# Capability methodology

How the coding / software-engineering capability layer is measured, served,
and reported. This layer is separate from the serving benchmark
(`docs/methodology.md`) and the two are never combined.

## Serving profile

The serving benchmark optimizes token throughput (`--ctx-size 4096`,
`--parallel 2`, continuous batching). Coding-agent workloads need a different
profile:

- `--parallel 1` — one agent trajectory is evaluated at a time.
- `--ctx-size 8192` (common agent context, if hardware permits).
- same IQ4_XS weights, same pinned llama.cpp build (upstream for the 8-9B
  cohort, XHToken fork for Spark), same GPU — no re-quantization.
- reasoning disabled (`--reasoning off`) for direct coding so models emit code
  rather than a chain of thought.

## Context admission

Before any agentic run, each model is served at a context ladder
(8192 / 12288 / 16384) under the agent profile and must answer a
near-full-context prompt without OOM or transport failure. Results are
recorded in `results/capability/current/admission/`.

- A model whose native context is ~4K (Yi-1.5-9B) cannot reach the common
  agent context and is marked `CONTEXT_INELIGIBLE` for long-horizon agent
  benchmarks (it still participates in direct coding).
- If Spark's transport instability prevents repository-agent use, it is marked
  `TRANSPORT_INELIGIBLE` — reported, not hidden.
- If KV-cache quantization is needed to fit a longer context, exactly one
  documented policy is used and recorded in the manifest. Models are not
  silently re-quantized.

## Agent harness

One pinned **mini-swe-agent** (`SWE-agent/mini-swe-agent` @ `04d809c`) with the
bash/text action interface (no model-specific function calling) drives every
repo-level comparison. The same prompt/config/action format is used across
models, so a model+scaffold change never contaminates a model comparison.

The harness is pointed at the local llama.cpp OpenAI-compatible endpoint
(`http://127.0.0.1:<port>/v1`) — zero local token cost, no external
credentials.

## Admission gates

Before expensive SWE runs, every model must pass, on a tiny controlled repo
task: endpoint works, harness connects, valid bash/action format, inspect
files, execute tests, edit a file, produce a patch, no context overflow, no
server restart/OOM, no parser failure. Only admitted models proceed.

## Subsets

Full sets (SWE-bench Verified 500, DeepSWE ~113, Multilingual 300,
Terminal-Bench, SWE-bench Pro 731, SWE-EVO) are not run in full on this
laptop. Deterministic subsets are selected with seed 42 and stratification by
repo / language / category (never cherry-picked), and only the task IDs are
committed (`evals/tasksets/`). Results are labeled exactly
`<benchmark> Local-N` and are not leaderboard-equivalent.

## Grading

- Direct coding: official EvalPlus / LiveCodeBench executors, `pass@1`
  (`temperature=0, n=1`). pass@k is never reported without k independent
  samples.
- SWE-bench / DeepSWE / Multilingual / Terminal-Bench: the official evaluators
  grade mini-swe-agent patches. No custom "looks correct" judge. DeepSWE uses
  the official Pier/Harbor task environments and verifiers (unmodified).

## Statistics and reporting

- Binary outcomes: `resolved count / attempted count`, resolved %, Wilson 95%
  interval. Never "100%" without `n`.
- Failure taxonomy separates model/agent failures
  (test failure, regression, patch invalid, no patch, protocol error, context
  limit, timeout) from infrastructure failures (model server error, OOM,
  environment error, verifier error). Infrastructure failures never silently
  count as model failures.

## Security / sandboxing

Repository-level benchmarks execute untrusted project code. Task/verifier
containers are treated as untrusted: no `$HOME`, SSH keys, git credentials,
`.env`, or HF tokens are mounted; the Docker socket is not exposed inside task
containers; external network access is disabled where the benchmark permits.
Only the host-side orchestrator controls Docker, and only the minimal route to
the local LLM endpoint is exposed.
