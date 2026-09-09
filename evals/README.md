# Capability evaluation

This directory implements the **coding / software-engineering capability
evaluation** layer. It is separate from the serving benchmark (`bench/`) and
measures a different thing: how well the local models write and modify code,
not how fast they serve tokens.

The two layers are never combined into one score.

## Layout

- `config.json` — pinned external benchmark versions, agent serving profile,
  deterministic subset specs.
- `runner.py` — serves the existing IQ4_XS models under a *separate* agent
  profile (parallel=1, longer context) and talks to the OpenAI-compatible
  endpoint. Model metadata is read from `configs/models.json`.
- `normalize.py` — result schema (`summary.tsv`, `tasks.tsv`, `manifest.json`),
  Wilson intervals, failure taxonomy.
- `direct_code.py` — EvalPlus (HumanEval+/MBPP+) generation + evaluation.
- `admit.py` — agent-context ladder admission + mini-swe-agent harness gates.
- `subsets.py` — deterministic (seed 42, stratified) task-subset selection.
- `tasksets/` — committed task-ID lists for each local subset.

## Results

- `results/capability/current/` — committed summaries, per-task outcomes,
  manifests.
- `results/capability/runs/` — raw trajectories/logs/samples (git-ignored).

## Benchmark classes

- **Direct coding** (EvalPlus, LiveCodeBench): model-only, temperature=0, n=1.
- **Agentic SWE** (SWE-bench Verified, DeepSWE, Multilingual, Terminal-Bench):
  model + mini-swe-agent harness + context policy + tool interaction. These are
  NOT pure model-intelligence scores.

## Important caveats

- Local subsets are named exactly `… Local-N` and are **not** official
  full-benchmark or leaderboard-equivalent scores.
- LiveCodeBench runs use a `LOCAL PROTOCOL` (n=1) and are not
  leaderboard-equivalent.
- SWE-bench Multimodal v2 is `NOT_APPLICABLE_NO_VISION` (models are text-only).
- No SLO "goodput" is fabricated; transport success rate ≠ SLO good-request
  fraction.
- Infrastructure failures (OOM, verifier errors, environment errors) are
  reported separately from model/agent failures and never silently count as
  model failures.

## Reproduce

```bash
make eval-setup      # clone/pin external benchmarks into .cache/evals/
make eval-admit      # agent-context + harness admission
make eval-code       # EvalPlus + LiveCodeBench (direct coding)
make eval-swe        # SWE-bench Verified Local-20
make eval-report     # regenerate the capability dashboard data
```

See `docs/capability-methodology.md` and `docs/benchmark-selection.md` for the
full methodology and benchmark-by-benchmark rationale.
