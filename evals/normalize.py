#!/usr/bin/env python3
"""Shared result-schema helpers for the capability evaluation.

Result layout (results/capability/current/<bench>/):
    summary.tsv    one row per model (or model+subset)
    tasks.tsv      one row per task/model
    manifest.json  full provenance

Statistics: binary outcomes -> resolved count + Wilson 95% interval.
Never report a percentage without n.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAP_RESULTS = ROOT / "results" / "capability" / "current"

# Common failure taxonomy (model/agent vs infrastructure).
MODEL_FAILURES = [
    "TEST_FAILURE", "REGRESSION", "PATCH_INVALID", "NO_PATCH",
    "AGENT_PROTOCOL_ERROR", "CONTEXT_LIMIT", "TIMEOUT",
]
INFRA_FAILURES = ["MODEL_SERVER_ERROR", "OOM", "ENVIRONMENT_ERROR", "VERIFIER_ERROR"]
ALL_FAILURES = ["RESOLVED"] + MODEL_FAILURES + INFRA_FAILURES


def wilson(n, k, z=1.96):
    """Wilson 95% score interval for k successes in n trials."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def pct(k, n):
    return round(100.0 * k / n, 1) if n else None


def sha256_of(text):
    return hashlib.sha256(text.encode()).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head():
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                       capture_output=True, text=True)
    return r.stdout.strip() or None


def load_models():
    with open(ROOT / "configs" / "models.json") as f:
        return json.load(f)


def load_evals_cfg():
    with open(ROOT / "evals" / "config.json") as f:
        return json.load(f)


def model_info(arm):
    m = next((x for x in load_models()["models"] if x["arm"] == arm), None)
    return m


def engine_commit(arm):
    m = model_info(arm)
    if not m:
        return None
    data = load_models()
    eng = data["cohorts"][m["cohort"]]["engine"]
    return data["engines"][eng].get("commit")


def make_manifest(benchmark, model_arm, extra=None):
    """Standard manifest for one model within one benchmark run."""
    cfg = load_evals_cfg()
    m = model_info(model_arm)
    b = cfg["benchmarks"].get(benchmark, {})
    man = {
        "benchmark": benchmark,
        "benchmark_version": b.get("version"),
        "benchmark_commit": b.get("commit"),
        "agent_scaffold": b.get("agent") or "none (direct coding)",
        "agent_version": None,
        "model": model_arm,
        "display_name": m.get("display_name") if m else model_arm,
        "gguf": m.get("gguf_filename") if m else None,
        "gguf_sha256": m.get("sha256") if m else None,
        "quantization": m.get("quantization") if m else None,
        "llama_cpp_commit": engine_commit(model_arm),
        "agent_context": cfg["agent_profile"]["ctx_size"],
        "kv_cache_policy": cfg["agent_profile"]["kv_cache_policy"],
        "generation": cfg["direct_coding_profile"]["generation"],
        "reasoning": "off",
        "hardware": "RTX 3060 Laptop 6 GiB",
        "run_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "project_git_commit": git_head(),
    }
    if extra:
        man.update(extra)
    return man


def write_summary(bench, rows, columns):
    """rows: list of dicts; columns: ordered keys to emit."""
    p = CAP_RESULTS / bench
    p.mkdir(parents=True, exist_ok=True)
    with open(p / "summary.tsv", "w") as f:
        f.write("\t".join(columns) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in columns) + "\n")


def write_tasks(bench, rows, columns):
    p = CAP_RESULTS / bench
    p.mkdir(parents=True, exist_ok=True)
    with open(p / "tasks.tsv", "w") as f:
        f.write("\t".join(columns) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in columns) + "\n")


def write_manifest(bench, manifest):
    p = CAP_RESULTS / bench
    p.mkdir(parents=True, exist_ok=True)
    with open(p / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
