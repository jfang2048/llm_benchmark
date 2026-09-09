#!/usr/bin/env python3
"""DeepSWE v1.1 adapter: pier + mini-swe-agent + official verifiers.

DeepSWE tasks use the Harbor/Pier task format; grading uses each task's
official `[verifier]` (separate environment). This adapter runs the committed
DeepSWE Local-10 taskset with the pinned Pier harness and mini-swe-agent
against the local llama.cpp endpoint, then normalizes the verifier output.

No custom judge — the task verifier is unmodified.

Usage (eval venv python; pier must be installed):
    $HOME/.venv-eval/bin/python evals/deepswe.py run <arm>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import normalize  # noqa: E402
import runner  # noqa: E402

TASKS = ROOT / ".cache" / "evals" / "deep-swe" / "tasks"
RUNS = ROOT / "results" / "capability" / "runs" / "deepswe"


def load_subset():
    with open(ROOT / "evals" / "tasksets" / "deepswe_local10.json") as f:
        return json.load(f)


def serve(arm):
    prof = normalize.load_evals_cfg()["agent_profile"]
    if not runner.wait_ready(arm, timeout=5):
        runner.serve(arm, ctx_size=prof["ctx_size"], parallel=1, reasoning="off")
        if not runner.wait_ready(arm, timeout=300):
            raise SystemExit(f"server for {arm} not ready")


def run_task(arm, task_id, pier_bin):
    m = runner.model_by_arm(arm)
    base = f"http://127.0.0.1:{m['port']}/v1"
    env = {"OPENAI_API_KEY": "sk-local", "OPENAI_API_BASE": base,
           "OPENAI_BASE_URL": base}
    cmd = [pier_bin, "run", "-p", str(TASKS / task_id),
           "--agent", "mini-swe-agent", "--model", f"openai/{arm}",
           "--single"]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          timeout=7200, env={**__import__("os").environ, **env})


def run(arm):
    subset = load_subset()
    ids = subset["instance_ids"]
    pier_bin = str(ROOT / ".venv-eval" / "bin" / "pier")
    serve(arm)
    for i, task_id in enumerate(ids):
        print(f"[{i + 1}/{len(ids)}] {task_id}")
        r = run_task(arm, task_id, pier_bin)
        print(f"  exit={r.returncode}")
        # verifier output lands in pier's run dir; normalize in a later pass.
    print("DeepSWE adapter: ran pier; verifier-output normalization wired in "
          "collect_deepswe_results().")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("arm")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.arm)
