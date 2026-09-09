#!/usr/bin/env python3
"""SWE-bench Verified runner: mini-swe-agent (patches) + official evaluator.

Pipeline per model:
  1. Read the committed deterministic subset (evals/tasksets/swe_verified_local20.json).
  2. Serve the model under the agent profile (parallel=1, reasoning off).
  3. Run mini-swe-agent batch inference (Docker, 1 worker) -> preds.json.
  4. Grade with the OFFICIAL swebench.harness.run_evaluation.
  5. Normalize into summary.tsv / tasks.tsv / manifest.json.

No custom judge. Infrastructure failures are recorded separately.

Usage (eval venv python):
    $HOME/venvs/eval/bin/python evals/swe.py run <arm>
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import normalize  # noqa: E402
import runner  # noqa: E402

EVAL_BIN = Path.home() / "venvs" / "eval" / "bin"
DATASET = "princeton-nlp/SWE-bench_Verified"
SPLIT = "test"
RUNS = ROOT / "results" / "capability" / "runs" / "swe-verified"


def load_subset(path):
    with open(path) as f:
        return json.load(f)


def filter_regex(instance_ids):
    return "^(?:" + "|".join(re.escape(i) for i in instance_ids) + ")$"


def serve(arm):
    profile = normalize.load_evals_cfg()["agent_profile"]
    if not runner.wait_ready(arm, timeout=5):
        runner.serve(arm, ctx_size=profile["ctx_size"], parallel=1, reasoning="off")
        if not runner.wait_ready(arm, timeout=300):
            raise SystemExit(f"server for {arm} not ready")


def run_agent(arm, instance_ids, preds_dir):
    """Run mini-swe-agent batch inference. Returns preds.json path."""
    m = runner.model_by_arm(arm)
    if not m:
        raise SystemExit(f"unknown arm {arm}")
    base = f"http://127.0.0.1:{m['port']}/v1"
    preds_dir = Path(preds_dir)
    preds_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(EVAL_BIN / "python"), "-m", "minisweagent.run.benchmarks.swebench",
        "--subset", "verified", "--split", SPLIT,
        "--filter", filter_regex(instance_ids),
        "-m", arm, "-w", "1", "-o", str(preds_dir),
        "-c", "swebench.yaml",
        "-c", "model.model_kwargs.custom_llm_provider=openai",
        "-c", f"model.model_kwargs.api_base={base}",
        "-c", "agent.max_iterations=50",
    ]
    print(" ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT, text=True, timeout=None)
    if r.returncode != 0:
        raise SystemExit(f"mini-swe-agent failed (exit {r.returncode})")
    return preds_dir / "preds.json"


def run_evaluator(preds_path, instance_ids, run_id):
    cmd = [
        str(EVAL_BIN / "python"), "-m", "swebench.harness.run_evaluation",
        "-d", DATASET, "-s", SPLIT,
        "-i", *instance_ids,
        "-p", str(preds_path),
        "--max_workers", "1", "--timeout", "1800",
        "-id", run_id,
    ]
    print(" ".join(cmd))
    r = subprocess.run(cmd, cwd=ROOT, text=True, timeout=None)
    if r.returncode != 0:
        raise SystemExit(f"swebench evaluator failed (exit {r.returncode})")
    return ROOT / "logs" / "evaluation" / run_id


def collect_reports(arm, run_id):
    """Read per-instance report.json produced by the official evaluator."""
    log_root = ROOT / "logs" / "evaluation" / run_id
    reports = {}
    if log_root.exists():
        for rp in log_root.rglob("report.json"):
            try:
                reports.update(json.loads(rp.read_text()))
            except Exception:
                continue
    return reports


def run(arm):
    subset = load_subset(ROOT / "evals" / "tasksets" / "swe_verified_local20.json")
    ids = subset["instance_ids"]
    run_id = f"{arm}-local20-{subset['task_ids_hash'][:8]}"

    serve(arm)
    preds = run_agent(arm, ids, RUNS / arm)
    run_evaluator(preds, ids, run_id)
    reports = collect_reports(arm, run_id)

    tasks = []
    resolved = 0
    n = 0
    for iid in ids:
        r = reports.get(iid, {})
        res = bool(r.get("resolved"))
        n += 1
        resolved += res
        f2p = r.get("f2p", {}) or {}
        p2p = r.get("p2p", {}) or {}
        f2p_pass = sum(1 for v in f2p.values() if v.get("success"))
        p2p_pass = sum(1 for v in p2p.values() if v.get("success"))
        tasks.append({
            "instance_id": iid,
            "model": arm,
            "resolved": res,
            "f2p_pass": f2p_pass, "f2p_total": len(f2p),
            "p2p_pass": p2p_pass, "p2p_total": len(p2p),
            "failure_category": "RESOLVED" if res else "TEST_FAILURE",
        })

    lo, hi = normalize.wilson(n, resolved)
    rows = [{
        "model": arm, "resolved": resolved, "n": n,
        "resolved_pct": normalize.pct(resolved, n),
        "wilson_lo": round(lo * 100, 1), "wilson_hi": round(hi * 100, 1),
        "subset": "SWE-bench Verified Local-20",
        "task_ids_hash": subset["task_ids_hash"],
    }]
    cols = ["model", "resolved", "n", "resolved_pct", "wilson_lo", "wilson_hi",
            "subset", "task_ids_hash"]
    normalize.write_summary("swe-verified", rows, cols)
    normalize.write_tasks("swe-verified", tasks,
                          ["instance_id", "model", "resolved", "f2p_pass",
                           "f2p_total", "p2p_pass", "p2p_total",
                           "failure_category"])
    man = normalize.make_manifest("swe_verified", arm, extra={
        "subset": "SWE-bench Verified Local-20",
        "task_ids_hash": subset["task_ids_hash"],
        "n": n, "agent_scaffold": "mini-swe-agent",
        "agent_version": "2.4.6",
    })
    normalize.write_manifest("swe-verified", man)
    print(f"SUMMARY {arm}: resolved {resolved}/{n} ({normalize.pct(resolved, n)}%)")


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
