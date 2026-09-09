#!/usr/bin/env python3
"""LiveCodeBench direct-coding pipeline (code generation, LOCAL PROTOCOL).

Uses the OFFICIAL LiveCodeBench prompt format and the OFFICIAL test-based
judge (check_correctness), but n=1 against the local llama.cpp endpoint.
This is labeled LOCAL PROTOCOL and is NOT leaderboard-equivalent (the official
leaderboard samples n>=20 and estimates pass@k).

Run with the eval venv python (needs livecodebench deps: datasets, openai):
    $HOME/venvs/eval/bin/python evals/livecodebench.py run <arm> --release release_v5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / ".cache" / "evals" / "LiveCodeBench"))

import normalize  # noqa: E402
import runner  # noqa: E402

RUNS = ROOT / "results" / "capability" / "runs" / "livecodebench"


def load_dataset(release):
    from lcb_runner.benchmarks.code_generation import load_code_generation_dataset
    return load_code_generation_dataset(release_version=release)


def build_prompt(problem):
    from lcb_runner.prompts.code_generation import (
        PromptConstants, get_generic_question_template_answer)
    return PromptConstants.SYSTEM_MESSAGE_GENERIC, \
        get_generic_question_template_answer(problem)


def extract_code(text):
    """Extract the first ```python ... ``` block (official delimiter)."""
    if "```" not in text:
        return text
    parts = text.split("```")
    for p in parts[1::2]:
        p = p.strip()
        if p.startswith("python"):
            p = p[6:].strip()
        if p:
            return p
    return ""


def grade(problem, code):
    from lcb_runner.evaluation.compute_code_generation_metrics import check_correctness
    try:
        res = check_correctness(problem, code, timeout=3, debug=False)
    except Exception:
        return None, None
    return res


def run(arm, release="release_v5", max_problems=None):
    problems = load_dataset(release)
    if max_problems:
        problems = problems[:max_problems]
    print(f"LiveCodeBench {release}: {len(problems)} problems for {arm}")

    profile = normalize.load_evals_cfg()["direct_coding_profile"]
    if not runner.wait_ready(arm, timeout=5):
        runner.serve(arm, ctx_size=profile["ctx_size"],
                     parallel=profile["parallel"], reasoning="off")
        if not runner.wait_ready(arm, timeout=300):
            raise SystemExit(f"server for {arm} not ready")

    tasks = []
    for p in problems:
        pid = p.question_id if hasattr(p, "question_id") else getattr(p, "question_id", "?")
        sys_msg, user = build_prompt(p)
        resp = runner.generate(arm, [[{"role": "system", "content": sys_msg},
                                      {"role": "user", "content": user}]],
                               temperature=0.0, n=1, max_tokens=2048, timeout=240)[0]
        text = runner.extract_text(resp)
        code = extract_code(text)
        passed, total = grade(p, code)
        ok = bool(passed is not None and total is not None and passed == total)
        tasks.append({
            "task_id": pid, "model": arm,
            "resolved": ok,
            "passed": passed if passed is not None else "",
            "total": total if total is not None else "",
            "release": release,
        })
        print(f"  {pid}: {'PASS' if ok else 'fail'} ({passed}/{total})")

    n = len(tasks)
    resolved = sum(1 for t in tasks if t["resolved"])
    lo, hi = normalize.wilson(n, resolved)
    rows = [{
        "model": arm, "resolved": resolved, "n": n,
        "pass_at_1": normalize.pct(resolved, n),
        "wilson_lo": round(lo * 100, 1), "wilson_hi": round(hi * 100, 1),
        "release": release, "protocol": "LOCAL PROTOCOL (n=1)",
    }]
    cols = ["model", "resolved", "n", "pass_at_1", "wilson_lo", "wilson_hi",
            "release", "protocol"]
    normalize.write_summary("livecodebench", rows, cols, key_cols=["model", "release"])
    normalize.write_tasks("livecodebench", tasks,
                          ["task_id", "model", "resolved", "passed", "total", "release"],
                          key_cols=["task_id", "model"])
    man = normalize.make_manifest("livecodebench", arm, extra={
        "release": release, "n": n, "protocol": "LOCAL PROTOCOL (n=1)",
    })
    normalize.write_manifest("livecodebench", man)
    print(f"SUMMARY {arm} {release}: pass@1 {resolved}/{n} "
          f"({normalize.pct(resolved, n)}%)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("arm")
    p.add_argument("--release", default="release_v5")
    p.add_argument("--max-problems", type=int, default=None)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.arm, a.release, a.max_problems)


if __name__ == "__main__":
    main()
