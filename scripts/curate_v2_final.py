#!/usr/bin/env python3
"""Curate the latest Benchmark v2 run per suite into results/v2/final/.

Copies only machine-readable summary files (no raw logs, per-request artifacts,
or GPU telemetry), mirroring how results/final/ curates the v1 run. The output
is committed for publication and consumed by scripts/generate_v2_report.py.

Usage:
    python3 scripts/curate_v2_final.py
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "results" / "v2" / "runs"
FINAL = ROOT / "results" / "v2" / "final"

MODES = ["capacity", "shape", "open-loop", "sessions", "startup", "soak", "backend"]

# Machine-readable summary files that are safe and meaningful to publish.
# (summary.txt and workload.sha256 embed the absolute run path and are excluded;
# the workload hash is already recorded in manifest.json.)
SUMMARY_FILES = [
    "manifest.json", "repeats.tsv", "aggregate.tsv", "resource_summary.tsv",
    "slo_summary.tsv", "sessions.tsv", "soak_summary.tsv", "startup.tsv",
    "error_details.tsv", "model_workload.jsonl", "workload_manifest.json",
]


def discover_latest():
    latest = {}
    for manifest in sorted(RUNS.glob("*/manifest.json")):
        try:
            m = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        mode = m.get("mode")
        if mode:
            latest[mode] = manifest.parent
    return latest


def main():
    latest = discover_latest()
    FINAL.mkdir(parents=True, exist_ok=True)
    curated = {}
    for mode in MODES:
        src = latest.get(mode)
        if src is None:
            print(f"WARN: no run for mode={mode}", file=sys.stderr)
            continue
        dest = FINAL / mode
        dest.mkdir(parents=True, exist_ok=True)
        for f in SUMMARY_FILES:
            p = src / f
            if p.exists():
                shutil.copy2(p, dest / f)
        curated[mode] = src.name
        print(f"curated {mode} <- {src.name}")
    (FINAL / "manifest.json").write_text(
        json.dumps({
            "schema_version": 1,
            "description": "Curated Benchmark v2 publication dataset (summary files only).",
            "modes": curated,
        }, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {FINAL / 'manifest.json'}")


if __name__ == "__main__":
    main()
