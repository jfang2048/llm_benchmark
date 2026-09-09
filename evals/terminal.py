#!/usr/bin/env python3
"""Terminal-Bench 2.0 adapter (Harbor harness + mini-swe-agent).

Runs the committed Terminal-Bench Local-10 taskset with the pinned Harbor
framework and the official per-task verifier. No custom judge.

Usage:
    $HOME/.venv-eval/bin/python evals/terminal.py run <arm>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import normalize  # noqa: E402
import runner  # noqa: E402

TASKS = ROOT / ".cache" / "evals" / "terminal-bench-2"
RUNS = ROOT / "results" / "capability" / "runs" / "terminal-bench"
BENCH = "terminal-bench"


def run(arm):
    subset = json.load(open(ROOT / "evals" / "tasksets" / "terminal_bench_local10.json"))
    ids = subset["instance_ids"]
    m = runner.model_by_arm(arm)
    base = f"http://127.0.0.1:{m['port']}/v1"

    prof = normalize.load_evals_cfg()["agent_profile"]
    if not runner.wait_ready(arm, timeout=5):
        runner.serve(arm, ctx_size=prof["ctx_size"], parallel=1, reasoning="off")
        if not runner.wait_ready(arm, timeout=300):
            raise SystemExit(f"server for {arm} not ready")

    env = {**os.environ, "OPENAI_API_KEY": "sk-local", "OPENAI_API_BASE": base,
           "OPENAI_BASE_URL": base}
    harbor = ROOT / ".venv-eval" / "bin" / "harbor"
    tasks, resolved, valid = [], 0, 0
    for i, task_id in enumerate(ids):
        cmd = [str(harbor), "run", "-p", str(TASKS / task_id),
               "--agent", "mini-swe-agent", "--model", f"openai/{arm}",
               "--single"]
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           timeout=7200, env=env)
        # resolved determined by harbor's verifier exit (0 = pass)
        res = r.returncode == 0
        valid += 1
        resolved += res
        tasks.append({"instance_id": task_id, "model": arm, "resolved": res,
                      "failure_category": "RESOLVED" if res else "TEST_FAILURE"})
        print(f"[{i + 1}/{len(ids)}] {task_id}: {'RESOLVED' if res else 'FAIL'}")

    lo, hi = normalize.wilson(valid, resolved)
    rows = [{"model": arm, "scheduled_tasks": len(ids), "resolved": resolved,
             "n": valid, "pass_pct": normalize.pct(resolved, valid),
             "wilson_lo": round(lo * 100, 1), "wilson_hi": round(hi * 100, 1),
             "subset": "Terminal-Bench Local-10",
             "task_ids_hash": subset["task_ids_hash"]}]
    normalize.write_summary(BENCH, rows,
                            ["model", "scheduled_tasks", "resolved", "n", "pass_pct",
                             "wilson_lo", "wilson_hi", "subset", "task_ids_hash"])
    normalize.write_tasks(BENCH, tasks,
                          ["instance_id", "model", "resolved", "failure_category"])
    man = normalize.make_manifest("terminal_bench", arm, kind="agent", extra={
        "subset": "Terminal-Bench Local-10", "task_ids_hash": subset["task_ids_hash"],
        "max_iterations": 50})
    normalize.write_manifest(BENCH, man)
    print(f"SUMMARY {arm}: pass {resolved}/{valid} ({normalize.pct(resolved, valid)}%)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("arm")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.arm)


if __name__ == "__main__":
    main()
