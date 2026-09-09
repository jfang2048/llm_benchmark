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


def run_fingerprint(components):
    """Deterministic protocol/run fingerprint from key run components."""
    s = json.dumps(components, sort_keys=True, default=str)
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def make_manifest(benchmark, model_arm, kind="direct", extra=None):
    """One run's manifest. `kind` = 'direct' (coding) or 'agent' (SWE).

    The two kinds record different, real values — never a serving-profile
    default copied from the other suite.
    """
    cfg = load_evals_cfg()
    m = model_info(model_arm)
    b = cfg["benchmarks"].get(benchmark, {})
    msa = cfg["benchmarks"].get("mini_swe_agent", {})

    if kind == "agent":
        prof = cfg["agent_profile"]
        base = {
            "benchmark": benchmark,
            "benchmark_version": b.get("version"),
            "benchmark_commit": b.get("commit"),
            "serving_profile": "agent_profile",
            "agent": b.get("agent") or "mini-swe-agent",
            "agent_commit": msa.get("commit"),
            "agent_version": msa.get("version"),
            "context": prof["ctx_size"],
            "parallel": prof["parallel"],
            "kv_cache_policy": prof["kv_cache_policy"],
            "generation": prof["generation"],
            "reasoning": "off",
            "max_iterations": None,
        }
    else:
        prof = cfg["direct_coding_profile"]
        base = {
            "benchmark": benchmark,
            "benchmark_version": b.get("version"),
            "benchmark_commit": b.get("commit"),
            "serving_profile": "direct_coding_profile",
            "agent": "none",
            "context": prof["ctx_size"],
            "parallel": prof["parallel"],
            "generation": prof["generation"],
            "reasoning": "off",
            "max_output_tokens": None,
            "prompt_protocol": "local chat protocol + official executor",
        }

    base.update({
        "model": model_arm,
        "display_name": m.get("display_name") if m else model_arm,
        "gguf": m.get("gguf_filename") if m else None,
        "gguf_sha256": m.get("sha256") if m else None,
        "quantization": m.get("quantization") if m else None,
        "engine_commit": engine_commit(model_arm),
        "hardware": "RTX 3060 Laptop 6 GiB",
        "run_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "project_git_commit": git_head(),
    })
    if extra:
        base.update(extra)
    return base


def _read_tsv(path):
    import csv
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _merge_rows(path, rows, columns, key_cols):
    """Upsert rows into a TSV by key_cols, preserving prior rows for other keys."""
    existing = {}
    for r in _read_tsv(path):
        existing[tuple(str(r.get(c, "")) for c in key_cols)] = r
    for r in rows:
        existing[tuple(str(r.get(c, "")) for c in key_cols)] = r
    with open(path, "w") as f:
        f.write("\t".join(columns) + "\n")
        for r in existing.values():
            f.write("\t".join(str(r.get(c, "")) for c in columns) + "\n")


def write_summary(bench, rows, columns, key_cols=None):
    """rows: list of dicts; columns: ordered keys to emit. Upserts by key_cols."""
    p = CAP_RESULTS / bench
    p.mkdir(parents=True, exist_ok=True)
    _merge_rows(p / "summary.tsv", rows, columns, key_cols or [columns[0]])


def write_tasks(bench, rows, columns, key_cols=None):
    p = CAP_RESULTS / bench
    p.mkdir(parents=True, exist_ok=True)
    default_key = []
    for cand in ("task_id", "instance_id"):
        if cand in columns:
            default_key.append(cand)
            break
    default_key.append("model")
    _merge_rows(p / "tasks.tsv", rows, columns, key_cols or default_key)


def write_manifest(bench, manifest):
    """Append one run to a multi-run manifest.json (Option A). Runs are keyed
    by a deterministic fingerprint so a later model never overwrites an
    earlier model's provenance."""
    p = CAP_RESULTS / bench
    p.mkdir(parents=True, exist_ok=True)
    path = p / "manifest.json"
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except Exception:
            existing = {}

    fp = run_fingerprint({k: manifest.get(k) for k in (
        "benchmark", "benchmark_commit", "model", "gguf_sha256",
        "engine_commit", "agent_commit", "context", "generation",
        "max_iterations", "max_output_tokens", "subset", "release")})
    manifest["run_fingerprint"] = fp

    runs = [r for r in existing.get("runs", []) if r.get("run_fingerprint") != fp]
    runs.append(manifest)

    out = {
        "benchmark": manifest.get("benchmark"),
        "benchmark_metadata": {
            "version": manifest.get("benchmark_version"),
            "commit": manifest.get("benchmark_commit"),
        },
        "runs": runs,
    }
    path.write_text(json.dumps(out, indent=2))
