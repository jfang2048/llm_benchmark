#!/usr/bin/env python3
"""One-task end-to-end SWE-bench validation (execution-order step 7).

Runs ONE SWE Verified instance (default: the first Local-20 task) through the
full pipeline — mini-swe-agent trajectory -> official evaluator -> report
parsing -> failure taxonomy — to validate the harness before the full Local-20.

Usage:
    .venv-eval/bin/python evals/validate_swe.py <arm> [instance_id]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import swe  # noqa: E402

RUNS = ROOT / "results" / "capability" / "runs" / "swe-verified" / "validate"


def main():
    arm = sys.argv[1]
    subset = json.load(open(ROOT / "evals" / "tasksets" / "swe_verified_local20.json"))
    instance_id = sys.argv[2] if len(sys.argv) > 2 else subset["instance_ids"][0]
    run_id = f"{arm}-validate-{instance_id}"

    swe.serve(arm)
    preds = swe.run_agent(arm, [instance_id], RUNS / arm, subset="verified",
                          split="test")
    swe.run_evaluator(preds, [instance_id], run_id, dataset="princeton-nlp/SWE-bench_Verified",
                      split="test")
    reports = swe.collect_reports(arm, run_id)
    r = reports.get(instance_id, {})
    print(json.dumps({
        "instance_id": instance_id,
        "report": r,
        "failure_category": swe.classify_report(r),
    }, indent=2))


if __name__ == "__main__":
    main()
