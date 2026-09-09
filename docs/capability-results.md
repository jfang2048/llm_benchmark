# Capability results

Coding / software-engineering capability results for the local models. This is
separate from the serving benchmark and is never combined with serving
throughput / TTFT / VRAM / energy into one score.

> Status: **in progress**. Direct coding (EvalPlus) is the first completed
> family; agentic SWE sweeps (SWE-bench Verified, DeepSWE, Multilingual,
> Terminal-Bench) are queued behind them on the shared GPU.

## Direct coding — EvalPlus

Protocol: `temperature=0, n=1`, reasoning off, official EvalPlus prompt +
executor. Values are pass@1 with Wilson 95% CI. `base → plus` is the drop in
points when the stronger `+` test set is applied (fragile solutions that only
pass weak tests).

| model | HumanEval | HumanEval+ | MBPP | MBPP+ | base→plus drop |
|---|---|---|---|---|---|
| Qwen3-8B | 84.1% (138/164) | 79.3% (130/164) | 79.1% (299/378) | 70.1% (265/378) | 4.9 / 9.0 pts |
| DeepSeek-R1-Distill-Llama-8B | — | — | — | — | — |
| GLM-4-9B-0414 | — | — | — | — | — |
| Yi-1.5-9B-Chat | — | — | — | — | — |
| Spark-X2.5-4B (REFERENCE / 4B) | — | — | — | — | — |

`—` = running or not yet run.

These are old, widely-memorized datasets; treat them as a floor check, not a
measure of contamination-resistant generalization.

## LiveCodeBench

`LOCAL PROTOCOL` (n=1), not leaderboard-equivalent. Pending.

## Agentic software engineering

- **SWE-bench Verified Local-20**: subset committed (seed 42, 12 repos, hash
  `8eaa41cb…`). Not yet run.
- **DeepSWE Local-10**: subset committed (seed 42, 2/language × 5 languages,
  hash `0f4242b0…`). Not yet run.
- **SWE-bench Multilingual Local-18**, **Terminal-Bench Local-10**,
  **SWE-bench Pro Local-10**, **SWE-EVO Local-4**: queued.

Local subsets are **not** official full-benchmark scores.

## Model eligibility (agentic)

Determined by context admission (not yet run). Expected: Yi-1.5-9B-Chat
(native ~4K) is `CONTEXT_INELIGIBLE` for long-horizon agent tasks; Spark
transport stability is to be verified (`TRANSPORT_INELIGIBLE` if it cannot
complete repository-agent trajectories).

## Not applicable

- SWE-bench Multimodal v2 — `NOT_APPLICABLE_NO_VISION` (text-only models).
- DeepSWE-Preview — a model, not the DeepSWE benchmark; not deployed.
