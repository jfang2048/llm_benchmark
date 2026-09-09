#!/usr/bin/env python3
"""SWE-bench Multilingual adapter.

Same official SWE-bench harness as evals/swe.py, but the multilingual dataset
and the committed SWE-Multilingual Local-18 taskset. mini-swe-agent generates
patches; the official evaluator grades them (no custom judge).

Usage:
    $HOME/.venv-eval/bin/python evals/multilingual.py run <arm>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import normalize  # noqa: E402
import runner  # noqa: E402
import swe  # noqa: E402  (reuse report parsing + evaluator)

DATASET = "SWE-bench/SWE-bench_Multilingual"
BENCH = "swe-multilingual"


def run(arm):
    subset = swe.load_subset(ROOT / "evals" / "tasksets" / "swe_multilingual_local18.json")
    ids = subset["instance_ids"]
    run_id = f"{arm}-ml18-{subset['task_ids_hash'][:8]}"

    swe.serve(arm)
    preds = swe.run_agent(arm, ids, ROOT / "results" / "capability" / "runs" / BENCH / arm,
                          subset="multilingual")
    swe.run_evaluator(preds, ids, run_id, dataset=DATASET)
    reports = swe.collect_reports(arm, run_id)

    tasks, resolved, valid, infra = [], 0, 0, 0
    for iid in ids:
        r = reports.get(iid, {})
        cat = swe.classify_report(r)
        res = cat == "RESOLVED"
        valid += cat != "MISSING_REPORT"
        resolved += res
        infra += cat == "ENVIRONMENT_ERROR"
        tasks.append({"instance_id": iid, "model": arm, "resolved": res,
                      "language": "", "failure_category": cat})

    lo, hi = normalize.wilson(valid, resolved)
    rows = [{"model": arm, "scheduled_tasks": len(ids),
             "validly_evaluated_tasks": valid, "resolved": resolved,
             "infrastructure_failures": infra,
             "resolved_pct": normalize.pct(resolved, valid),
             "wilson_lo": round(lo * 100, 1), "wilson_hi": round(hi * 100, 1),
             "subset": "SWE-Multilingual Local-18",
             "task_ids_hash": subset["task_ids_hash"]}]
    normalize.write_summary(BENCH, rows,
                            ["model", "scheduled_tasks", "validly_evaluated_tasks",
                             "resolved", "infrastructure_failures", "resolved_pct",
                             "wilson_lo", "wilson_hi", "subset", "task_ids_hash"])
    normalize.write_tasks(BENCH, tasks,
                          ["instance_id", "model", "resolved", "language",
                           "failure_category"])
    man = normalize.make_manifest("swe_multilingual", arm, kind="agent", extra={
        "subset": "SWE-Multilingual Local-18", "task_ids_hash": subset["task_ids_hash"],
        "scheduled_tasks": len(ids), "max_iterations": 50})
    normalize.write_manifest(BENCH, man)
    print(f"SUMMARY {arm}: resolved {resolved}/{valid} ({normalize.pct(resolved, valid)}%)")


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
