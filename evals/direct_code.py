#!/usr/bin/env python3
"""Direct coding evaluation (EvalPlus: HumanEval+/MBPP+).

Protocol: temperature=0, n=1, reasoning off, official EvalPlus prompt format,
official EvalPlus executor for grading. Generates completions against the
local llama.cpp OpenAI-compatible endpoint, then grades with evalplus.

Run with the eval venv python (has evalplus installed):
    $HOME/venvs/aiperf/bin/python evals/direct_code.py gen qwen3_8b humaneval
    $HOME/venvs/aiperf/bin/python evals/direct_code.py eval humaneval <samples.jsonl>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

from evalplus.data import get_human_eval_plus, get_mbpp_plus  # noqa: E402
from evalplus.sanitize import sanitize  # noqa: E402

import normalize  # noqa: E402
import runner  # noqa: E402

INSTRUCTION = ("Please provide a self-contained Python script that solves the "
               "following problem in a markdown code block:")
SYSTEM = "You are a helpful assistant good at coding."
RUNS = ROOT / "results" / "capability" / "runs" / "evalplus"


def problems_for(dataset):
    if dataset == "humaneval":
        return get_human_eval_plus()
    if dataset == "mbpp":
        return get_mbpp_plus()
    raise SystemExit(f"unknown dataset {dataset}")


def build_prompt(problem):
    p = problem["prompt"].strip()
    return (SYSTEM, INSTRUCTION + f"\n```python\n{p}\n```")


def gen(arm, dataset, max_tokens=768):
    problems = problems_for(dataset)
    out_dir = RUNS / arm
    out_dir.mkdir(parents=True, exist_ok=True)
    samples_path = out_dir / f"{dataset}.jsonl"

    done = {}
    if samples_path.exists():
        for line in open(samples_path):
            done[json.loads(line)["task_id"]] = True

    profile = normalize.load_evals_cfg()["direct_coding_profile"]
    if not runner.wait_ready(arm, timeout=5):
        runner.serve(arm, ctx_size=profile["ctx_size"],
                     parallel=profile["parallel"], reasoning="off")
        if not runner.wait_ready(arm, timeout=300):
            raise SystemExit(f"server for {arm} did not become ready")

    # Pre-build prompts in task order.
    items = [(tid, p) for tid, p in problems.items() if tid not in done]
    print(f"{arm} {dataset}: {len(items)} to generate, {len(done)} cached")

    msgs = []
    for tid, p in items:
        sys_, user = build_prompt(p)
        msgs.append((tid, p, [{"role": "system", "content": sys_},
                              {"role": "user", "content": user}]))

    with open(samples_path, "a") as f:
        for tid, p, m in msgs:
            impl = None
            for attempt in range(2):
                resp = runner.generate(arm, [m], temperature=0.0, n=1,
                                       max_tokens=max_tokens, timeout=180)[0]
                if "error" not in resp:
                    impl = runner.extract_text(resp)
                    break
                # request failed/timed out: restart the server once and retry
                print(f"  retry {tid} (attempt {attempt + 1}): "
                      f"{resp.get('error', '')[:80]}")
                runner.serve(arm, ctx_size=profile["ctx_size"],
                             parallel=profile["parallel"], reasoning="off")
                runner.wait_ready(arm, timeout=300)
            if impl is None:
                impl = ""
            sol = sanitize(impl, entrypoint=p["entry_point"])
            f.write(json.dumps({"task_id": tid, "solution": sol}) + "\n")
            f.flush()
    print(f"wrote {samples_path}")
    return str(samples_path)


def eval_(dataset, samples):
    results_path = samples.replace(".jsonl", "_eval_results.json")
    # reuse existing eval results if present (idempotent re-run)
    if Path(results_path).exists():
        print(f"reusing existing eval results {results_path}")
        return results_path
    r = subprocess.run(
        [sys.executable, "-m", "evalplus.evaluate",
         "--dataset", dataset, "--samples", samples, "--i-just-wanna-run"],
        capture_output=True, text=True)
    print(r.stdout[-3000:])
    if r.returncode != 0:
        print(r.stderr[-2000:], file=sys.stderr)
        raise SystemExit("evalplus.evaluate failed")
    return results_path


def parse_eval(results_path, dataset):
    """Return (base_pass_count, plus_pass_count, n_tasks, task_rows).

    evalplus v0.3.1 writes eval[tid] = [ {base_status, plus_status, ...}, ... ]
    (one dict per sample). pass@1 uses the first sample of each task."""
    with open(results_path) as f:
        res = json.load(f)
    ev = res["eval"]
    base_ok = 0
    plus_ok = 0
    tasks = []
    for tid, samples in ev.items():
        s = samples[0] if isinstance(samples, list) and samples else samples
        b = s.get("base_status") == "pass"
        pp = s.get("plus_status") == "pass"
        base_ok += b
        plus_ok += pp
        tasks.append({"task_id": tid, "base_pass": b, "plus_pass": pp})
    return base_ok, plus_ok, len(ev), tasks


def run(arm, dataset):
    samples = gen(arm, dataset)
    results_path = eval_(dataset, samples)
    base_ok, plus_ok, n, tasks = parse_eval(results_path, dataset)

    ci_b = normalize.wilson(n, base_ok)
    ci_p = normalize.wilson(n, plus_ok)
    rows = [{
        "model": arm,
        "dataset": dataset,
        "base": "HumanEval" if dataset == "humaneval" else "MBPP",
        "plus": "HumanEval+" if dataset == "humaneval" else "MBPP+",
        "base_pass_at_1": normalize.pct(base_ok, n),
        "plus_pass_at_1": normalize.pct(plus_ok, n),
        "base_wilson_lo": round(ci_b[0] * 100, 1),
        "base_wilson_hi": round(ci_b[1] * 100, 1),
        "plus_wilson_lo": round(ci_p[0] * 100, 1),
        "plus_wilson_hi": round(ci_p[1] * 100, 1),
        "n": n,
        "drop_base_to_plus_pts": round(normalize.pct(base_ok - plus_ok, n), 1),
    }]
    cols = ["model", "dataset", "base", "plus", "base_pass_at_1",
            "plus_pass_at_1", "base_wilson_lo", "base_wilson_hi",
            "plus_wilson_lo", "plus_wilson_hi", "n", "drop_base_to_plus_pts"]
    normalize.write_summary("evalplus", rows, cols)

    task_cols = ["task_id", "model", "base_pass", "plus_pass"]
    task_rows = [{**t, "model": arm} for t in tasks]
    normalize.write_tasks("evalplus", task_rows, task_cols)

    man = normalize.make_manifest("evalplus", arm, extra={
        "dataset": dataset, "n": n, "protocol": "temp=0, n=1, reasoning off",
    })
    normalize.write_manifest("evalplus", man)
    print(f"SUMMARY {arm} {dataset}: base {base_ok}/{n} ({normalize.pct(base_ok, n)}%), "
          f"plus {plus_ok}/{n} ({normalize.pct(plus_ok, n)}%)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("gen")
    p.add_argument("arm")
    p.add_argument("dataset", choices=["humaneval", "mbpp"])
    p.add_argument("--max-tokens", type=int, default=768)
    p = sub.add_parser("run")
    p.add_argument("arm")
    p.add_argument("dataset", choices=["humaneval", "mbpp"])
    a = ap.parse_args()
    if a.cmd == "gen":
        gen(a.arm, a.dataset, a.max_tokens)
    elif a.cmd == "run":
        run(a.arm, a.dataset)


if __name__ == "__main__":
    main()
