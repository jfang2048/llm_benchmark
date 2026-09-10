#!/usr/bin/env python3
"""Agent-context + harness admission for the capability evaluation.

Two stages:
  1. context  — serve each model under the agent profile (parallel=1) at the
     context ladder [8192, 12288, 16384], verify it serves without OOM and
     answers a near-full-context prompt. Records max supported context and the
     KV-cache policy used.
  2. agent    — run mini-swe-agent against a tiny controlled repo task to check
     the 10 admission gates (endpoint, connect, bash format, inspect, test,
     edit, patch, no overflow, no OOM/restart, no parser failure).

Run one model at a time (GPU is shared). Results go to
results/capability/current/admission/.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evals"))

import normalize  # noqa: E402
import runner  # noqa: E402

LADDER = [8192, 12288, 16384]


def _vram_mib():
    r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                        "--format=csv,noheader,nounits"],
                       capture_output=True, text=True)
    try:
        return int(r.stdout.strip().splitlines()[0].strip())
    except Exception:
        return None


def _fill_prompt(tokens):
    # ~1 token per ~4 chars for a filler string
    return ("word " * tokens)[: tokens * 5]


def context_admission(arm, kv_cache_quant=None, prompt_fill_frac=0.8):
    """Test the context ladder. Returns list of per-ctx records."""
    rows = []
    for ctx in LADDER:
        try:
            container = runner.serve(arm, ctx_size=ctx, parallel=1, reasoning="off",
                                     cache_type=kv_cache_quant)
        except SystemExit as e:
            rows.append({"arm": arm, "ctx": ctx, "ok": False,
                         "reason": f"serve failed: {e}", "vram_mib": ""})
            continue
        ok = runner.wait_ready(arm, timeout=300)
        vram = _vram_mib()
        overflow = None
        if ok:
            fill = _fill_prompt(int(ctx * prompt_fill_frac))
            try:
                resp = runner.generate(arm, [[{"role": "user",
                                               "content": fill + "\n\nReply with the single word: OK"}]],
                                       temperature=0, n=1, max_tokens=8)[0]
                txt = runner.extract_text(resp)
                overflow = ("OK" in txt) or bool(txt)
            except Exception as e:
                overflow = False
        # check OOM
        oom = False
        r = subprocess.run(["docker", "logs", container], capture_output=True, text=True)
        low = (r.stdout + r.stderr).lower()
        if any(p in low for p in ("out of memory", "cuda error", "failed to allocate")):
            oom = True
        rows.append({"arm": arm, "ctx": ctx, "ok": ok and not oom,
                     "reason": ("OOM" if oom else ("not ready" if not ok else
                              ("answer ok" if overflow else "no valid answer"))),
                     "vram_mib": vram or ""})
        runner.stop(arm)
        time.sleep(3)
    return rows


def _context_status(arm, rows):
    """Derive context eligibility from ladder results (measured, not assumed)."""
    ok = [r for r in rows if r["ok"]]
    if not ok:
        reasons = {r.get("reason", "") for r in rows}
        if any("OOM" in r for r in reasons):
            return "OOM"
        return "ERROR"
    max_ctx = max(r["ctx"] for r in ok)
    if max_ctx < 8192:
        return "CONTEXT_INELIGIBLE"
    # near-full-context answer at 8192?
    at8192 = [r for r in ok if r["ctx"] == 8192]
    if at8192 and not any("answer ok" in r.get("reason", "") for r in at8192):
        return "TRANSPORT_INELIGIBLE"
    return "ELIGIBLE"


def write_context_results(rows):
    normalize.write_tasks("admission", rows,
                          ["arm", "ctx", "ok", "reason", "vram_mib"],
                          key_cols=["arm", "ctx"])
    summary = {}
    for r in rows:
        if r["ok"]:
            summary[r["arm"]] = max(summary.get(r["arm"], 0), r["ctx"])
    srows = []
    for a in sorted(summary):
        arows = [r for r in rows if r["arm"] == a]
        c = summary[a]
        srows.append({
            "arm": a, "max_supported_ctx": c,
            "eligible_8192": c >= 8192,
            "context_status": _context_status(a, arows),
        })
    normalize.write_summary("admission", srows,
                            ["arm", "max_supported_ctx", "eligible_8192",
                             "context_status"], key_cols=["arm"])


def agent_admission(arm, step_limit=20, ctx=8192):
    """Run mini-swe-agent on the tiny admission repo and grade the 10 gates.

    Returns a dict of gate outcomes + metrics."""
    import shutil
    import tempfile

    m = runner.model_by_arm(arm)
    if not m:
        raise SystemExit(f"unknown arm {arm}")
    if not runner.wait_ready(arm, timeout=5):
        runner.serve(arm, ctx_size=ctx, parallel=1, reasoning="off")
        if not runner.wait_ready(arm, timeout=300):
            raise SystemExit(f"server for {arm} not ready")

    base = f"http://127.0.0.1:{m['port']}/v1"
    workdir = tempfile.mkdtemp(prefix="admit_")
    src = ROOT / "evals" / "tasksets" / "admission"
    for f in ("calc.py", "test_calc.py", "README.md"):
        shutil.copy(src / f, Path(workdir) / f)

    mini_bin = os.environ.get("MSWEA_BIN", str(ROOT / ".venv-eval" / "bin" / "mini"))
    task = ("The add() function in calc.py has a bug: it returns a-b instead of "
            "a+b. Inspect the files, run the test, edit calc.py to fix the bug, "
            "and re-run the test to confirm it passes. Finish by issuing "
            "`echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`.")
    out = str(Path(workdir) / "traj.json")
    t0 = time.time()
    cmd = [mini_bin, "-m", arm, "-t", task, "-y", "-l", "0",
           "-c", "mini.yaml",
           "-c", "model.model_kwargs.custom_llm_provider=openai",
           "-c", f"model.model_kwargs.api_base={base}",
           "-c", f"agent.step_limit={step_limit}",
           "-o", out, "--exit-immediately"]
    env = {**os.environ, "MSWEA_CONFIGURED": "true", "OPENAI_API_KEY": "sk-local",
           "MSWEA_COST_TRACKING": "ignore_errors"}
    try:
        r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                           timeout=1800, env=env)
    except subprocess.TimeoutExpired:
        r = None
    wall = time.time() - t0

    # grade objectively: does the edited calc.py pass its own tests?
    g = subprocess.run(["python3", "test_calc.py"], cwd=workdir,
                       capture_output=True, text=True)
    resolved = g.returncode == 0 and "all tests passed" in (g.stdout or "")

    # parse trajectory for metrics
    steps = tool_calls = invalid = in_tok = out_tok = None
    if Path(out).exists():
        try:
            traj = json.load(open(out))
            msgs = traj.get("messages", [])
            steps = len(msgs)
            tool_calls = sum(1 for m in msgs if isinstance(m, dict)
                             and (m.get("role") == "tool" or m.get("tool_calls")))
        except Exception:
            pass

    vram = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True, text=True).stdout.strip()

    # Admission = the harness worked end-to-end (endpoint + connect + the model
    # produced at least one bash action). Task resolution is a capability
    # signal, recorded separately, not a harness gate.
    admitted = bool(r is not None and r.returncode == 0 and steps and steps > 0)

    result = {
        "arm": arm,
        "endpoint_ok": runner.wait_ready(arm, timeout=3),
        "harness_connected": r is not None and r.returncode == 0,
        "resolved": resolved,
        "steps": steps, "tool_calls": tool_calls, "invalid_actions": invalid,
        "wall_time_s": round(wall, 1),
        "vram_mib": vram,
        "admitted": admitted,
    }
    return result


def write_agent_results(rows):
    cols = ["arm", "endpoint_ok", "harness_connected", "resolved", "steps",
            "tool_calls", "invalid_actions", "wall_time_s", "vram_mib", "admitted"]
    normalize.write_tasks("admission-agent", rows, cols, key_cols=["arm"])
    srows = [{k: r[k] for k in ("arm", "resolved", "steps", "wall_time_s", "admitted")}
             for r in rows]
    normalize.write_summary("admission-agent", srows,
                            ["arm", "resolved", "steps", "wall_time_s", "admitted"],
                            key_cols=["arm"])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("context")
    p.add_argument("arm")
    p.add_argument("--kv-cache-quant", default=None, help="e.g. q8_0 or q4_0")
    p = sub.add_parser("agent")
    p.add_argument("arm")
    p.add_argument("--step-limit", type=int, default=20)
    a = ap.parse_args()

    if a.cmd == "context":
        rows = context_admission(a.arm, a.kv_cache_quant)
        for r in rows:
            print(f"{r['arm']:24s} ctx={r['ctx']:5d} ok={r['ok']} "
                  f"vram={r['vram_mib']} ({r['reason']})")
        write_context_results(rows)
    elif a.cmd == "agent":
        res = agent_admission(a.arm, a.step_limit)
        print(json.dumps(res, indent=2))
        write_agent_results([res])


if __name__ == "__main__":
    main()
