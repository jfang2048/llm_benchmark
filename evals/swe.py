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
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import normalize  # noqa: E402
import runner  # noqa: E402

EVAL_BIN = ROOT / ".venv-eval" / "bin"
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
        runner.serve(arm, ctx_size=profile["ctx_size"], parallel=1, reasoning="auto")
        if not runner.wait_ready(arm, timeout=300):
            raise SystemExit(f"server for {arm} not ready")


def run_agent(arm, instance_ids, preds_dir, subset="verified", dataset=None, split=None):
    """Run mini-swe-agent batch inference. Returns preds.json path."""
    m = runner.model_by_arm(arm)
    if not m:
        raise SystemExit(f"unknown arm {arm}")
    base = f"http://127.0.0.1:{m['port']}/v1"
    sp = split or SPLIT
    preds_dir = Path(preds_dir)
    preds_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(EVAL_BIN / "python"), "-m", "minisweagent.run.benchmarks.swebench",
        "--subset", subset, "--split", sp,
        "--filter", filter_regex(instance_ids),
        "-m", arm, "-w", "1", "-o", str(preds_dir),
        "-c", "swebench.yaml",
        "-c", "model.model_kwargs.custom_llm_provider=openai",
        "-c", f"model.model_kwargs.api_base={base}",
        "-c", "agent.max_iterations=50",
    ]
    print(" ".join(cmd))
    env = {**os.environ, "MSWEA_CONFIGURED": "true", "OPENAI_API_KEY": "sk-local",
           "MSWEA_COST_TRACKING": "ignore_errors"}
    r = subprocess.run(cmd, cwd=ROOT, text=True, timeout=None, env=env)
    if r.returncode != 0:
        raise SystemExit(f"mini-swe-agent failed (exit {r.returncode})")
    return preds_dir / "preds.json"


def run_evaluator(preds_path, instance_ids, run_id, dataset=None, split=None):
    ds = dataset or DATASET
    sp = split or SPLIT
    cmd = [
        str(EVAL_BIN / "python"), "-m", "swebench.harness.run_evaluation",
        "-d", ds, "-s", sp,
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


def classify_report(r):
    """Map an official SWE-bench report dict to a failure category.

    Order matters: infra failures are reported separately from model failures.
    """
    if not r:
        return "MISSING_REPORT"  # no report.json -> evaluation did not complete
    if r.get("infra_failure"):
        return "ENVIRONMENT_ERROR"
    if r.get("resolved"):
        return "RESOLVED"
    if r.get("patch_is_None") or not r.get("patch_exists"):
        return "NO_PATCH"
    if not r.get("patch_successfully_applied"):
        return "PATCH_INVALID"
    return "TEST_FAILURE"


def run(arm):
    subset = load_subset(ROOT / "evals" / "tasksets" / "swe_verified_local20.json")
    ids = subset["instance_ids"]
    run_id = f"{arm}-local20-{subset['task_ids_hash'][:8]}"

    serve(arm)
    preds = run_agent(arm, ids, RUNS / arm)
    run_evaluator(preds, ids, run_id)
    reports = collect_reports(arm, run_id)

    tasks = []
    resolved = valid = infra = 0
    for iid in ids:
        r = reports.get(iid, {})
        cat = classify_report(r)
        res = cat == "RESOLVED"
        valid += 1 if cat != "MISSING_REPORT" else 0
        resolved += res
        infra += 1 if cat in ("ENVIRONMENT_ERROR",) else 0
        ts = r.get("tests_status", {}) or {}
        f2p = ts.get("FAIL_TO_PASS", {}) or {}
        p2p = ts.get("PASS_TO_PASS", {}) or {}
        tasks.append({
            "instance_id": iid, "model": arm,
            "resolved": res,
            "patch_exists": bool(r.get("patch_exists")),
            "patch_applied": bool(r.get("patch_successfully_applied")),
            "f2p_pass": len(f2p.get("success", [])),
            "f2p_total": len(f2p.get("success", [])) + len(f2p.get("failure", [])),
            "p2p_pass": len(p2p.get("success", [])),
            "p2p_total": len(p2p.get("success", [])) + len(p2p.get("failure", [])),
            "evaluation_completed": cat != "MISSING_REPORT",
            "failure_category": cat,
        })

    model_failures = len(tasks) - resolved - infra
    lo, hi = normalize.wilson(valid, resolved)
    rows = [{
        "model": arm,
        "scheduled_tasks": len(ids),
        "validly_evaluated_tasks": valid,
        "resolved": resolved,
        "model_failures": model_failures,
        "infrastructure_failures": infra,
        "resolved_pct": normalize.pct(resolved, valid),
        "wilson_lo": round(lo * 100, 1),
        "wilson_hi": round(hi * 100, 1),
        "coverage_pct": normalize.pct(valid, len(ids)),
        "subset": "SWE-bench Verified Local-20",
        "task_ids_hash": subset["task_ids_hash"],
    }]
    cols = ["model", "scheduled_tasks", "validly_evaluated_tasks", "resolved",
            "model_failures", "infrastructure_failures", "resolved_pct",
            "wilson_lo", "wilson_hi", "coverage_pct", "subset", "task_ids_hash"]
    normalize.write_summary("swe-verified", rows, cols)
    normalize.write_tasks("swe-verified", tasks,
                          ["instance_id", "model", "resolved", "patch_exists",
                           "patch_applied", "f2p_pass", "f2p_total", "p2p_pass",
                           "p2p_total", "evaluation_completed",
                           "failure_category"])
    man = normalize.make_manifest("swe_verified", arm, kind="agent", extra={
        "subset": "SWE-bench Verified Local-20",
        "task_ids_hash": subset["task_ids_hash"],
        "scheduled_tasks": len(ids),
        "max_iterations": 50,
    })
    normalize.write_manifest("swe-verified", man)
    print(f"SUMMARY {arm}: resolved {resolved}/{valid} valid "
          f"({normalize.pct(resolved, valid)}%), infra {infra}, "
          f"coverage {valid}/{len(ids)}")


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
