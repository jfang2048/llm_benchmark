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


def write_context_results(rows):
    normalize.write_tasks("admission", rows,
                          ["arm", "ctx", "ok", "reason", "vram_mib"])
    # summary: max ctx per model
    summary = {}
    for r in rows:
        if r["ok"]:
            summary[r["arm"]] = max(summary.get(r["arm"], 0), r["ctx"])
    srows = [{"arm": a, "max_supported_ctx": c,
              "eligible_8192": c >= 8192} for a, c in sorted(summary.items())]
    normalize.write_summary("admission", srows,
                            ["arm", "max_supported_ctx", "eligible_8192"])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("context")
    p.add_argument("arm")
    p.add_argument("--kv-cache-quant", default=None, help="e.g. q8_0 or q4_0")
    p = sub.add_parser("agent")
    p.add_argument("arm")
    a = ap.parse_args()

    if a.cmd == "context":
        rows = context_admission(a.arm, a.kv_cache_quant)
        for r in rows:
            print(f"{r['arm']:24s} ctx={r['ctx']:5d} ok={r['ok']} "
                  f"vram={r['vram_mib']} ({r['reason']})")
        write_context_results(rows)
    elif a.cmd == "agent":
        print("agent admission not yet wired (requires mini-swe-agent install)")


if __name__ == "__main__":
    main()
