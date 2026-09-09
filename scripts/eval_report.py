#!/usr/bin/env python3
"""Normalize results/capability/current/ into docs/data/capability.json.

Reads the committed summary.tsv / tasks.tsv / manifest.json per benchmark and
emits one dataset for the capability side of the dashboard. No benchmark values
are hardcoded here. Sections render only when data exist.

Run: python3 scripts/eval_report.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAP = ROOT / "results" / "capability" / "current"
DOCS = ROOT / "docs"
OUT = DOCS / "data" / "capability.json"

MODELS = ROOT / "configs" / "models.json"


def read_tsv(path):
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f, delimiter="\t"))


def read_manifest(path):
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def load_models():
    with open(MODELS) as f:
        data = json.load(f)
    cur = set(data["cohorts"].keys()) - {"historical_4b"}
    out = []
    for m in data["models"]:
        if m.get("enabled") and m.get("cohort") in cur:
            out.append({
                "arm": m["arm"], "display_name": m["display_name"],
                "context_length": m.get("context_length"),
                "quantization": m.get("quantization"),
                "is_reference": m.get("cohort") == "spark_reference",
                "params_b": round(m.get("actual_parameter_count", 0) / 1e9, 2),
            })
    return out


def build():
    models = load_models()
    arms = [m["arm"] for m in models]

    data = {
        "models": models,
        "benchmarks": {},
        "overview": {},       # arm -> {column_key: {metric, value, n, wilson_lo, wilson_hi}}
        "overview_columns": [
            ["humaneval_plus", "HumanEval+ pass@1"],
            ["mbpp_plus", "MBPP+ pass@1"],
            ["livecodebench", "LiveCodeBench pass@1"],
            ["swe-verified", "SWE Verified resolved %"],
            ["deepswe", "DeepSWE resolved %"],
            ["swe-multilingual", "Multilingual resolved %"],
            ["terminal-bench", "Terminal-Bench pass %"],
            ["swe-pro", "SWE Pro resolved %"],
            ["swe-evo", "SWE-EVO resolved %"],
        ],
        "tasks": [],          # task-explorer rows
        "failure_taxonomy": {},  # arm -> {category: count}
    }

    def set_overview(arm, key, value, n, metric, wilson_lo=None, wilson_hi=None):
        data["overview"].setdefault(arm, {})[key] = {
            "metric": metric, "value": value, "n": n,
            "wilson_lo": wilson_lo, "wilson_hi": wilson_hi,
        }

    # ---- evalplus ----
    eps = read_tsv(CAP / "evalplus" / "summary.tsv")
    ept = read_tsv(CAP / "evalplus" / "tasks.tsv")
    data["benchmarks"]["evalplus"] = {"summary": eps, "tasks": ept}
    for row in eps:
        arm = row["model"]
        n = int(row["n"])
        base_name = "HumanEval" if row["dataset"] == "humaneval" else "MBPP"
        set_overview(arm, f"{row['dataset']}_plus", float(row["plus_pass_at_1"]),
                     n, f"{base_name}+ pass@1",
                     float(row["plus_wilson_lo"]), float(row["plus_wilson_hi"]))
    for t in ept:
        data["tasks"].append({
            "benchmark": "evalplus", "task_id": t["task_id"], "model": t["model"],
            "repo": "", "language": "python",
            "resolved": bool(t["plus_pass"] == "True"),
            "metric": "pass@1",
        })

    # ---- generic reader for agentic benchmarks ----
    def ingest(bench, metric_label, resolved_field="resolved"):
        s = read_tsv(CAP / bench / "summary.tsv")
        t = read_tsv(CAP / bench / "tasks.tsv")
        data["benchmarks"][bench] = {"summary": s, "tasks": t,
                                     "manifest": read_manifest(CAP / bench / "manifest.json")}
        for row in s:
            arm = row["model"]
            n = int(row.get("n", row.get("attempted", 0)) or 0)
            k = int(row.get("resolved", row.get("pass", 0)) or 0)
            val = (k / n * 100 if n else None)
            set_overview(arm, bench, val, n, metric_label,
                         float(row["wilson_lo"]) if row.get("wilson_lo") not in (None, "") else None,
                         float(row["wilson_hi"]) if row.get("wilson_hi") not in (None, "") else None)
            # keep resolved/n for the per-benchmark section renderer
            if bench not in data["benchmarks"]:
                data["benchmarks"][bench] = {}
            data["benchmarks"][bench].setdefault("summary_meta", []).append({
                "model": arm, "resolved": k, "n": n,
                "wilson_lo": row.get("wilson_lo"), "wilson_hi": row.get("wilson_hi"),
            })
        for trow in t:
            cat = trow.get("failure_category", "")
            if cat:
                data["failure_taxonomy"].setdefault(trow["model"], {})
                data["failure_taxonomy"][trow["model"]][cat] = \
                    data["failure_taxonomy"][trow["model"]].get(cat, 0) + 1
            data["tasks"].append({
                "benchmark": bench, "task_id": trow.get("task_id", trow.get("instance_id", "")),
                "model": trow.get("model"), "repo": trow.get("repo", ""),
                "language": trow.get("language", ""),
                "resolved": str(trow.get(resolved_field, "")).lower() in
                            ("true", "1", "resolved", "pass"),
                "metric": metric_label,
                "steps": trow.get("agent_steps", ""), "wall_time": trow.get("wall_time", ""),
                "input_tokens": trow.get("input_tokens", ""),
                "output_tokens": trow.get("output_tokens", ""),
                "failure_category": cat,
            })

    for bench, label in [
        ("swe-verified", "resolved %"), ("deepswe", "resolved %"),
        ("swe-multilingual", "resolved %"), ("terminal-bench", "pass %"),
        ("swe-pro", "resolved %"), ("swe-evo", "resolved %"),
        ("livecodebench", "pass@1"),
    ]:
        if (CAP / bench / "summary.tsv").exists():
            ingest(bench, label)

    data["task_count"] = len(data["tasks"])
    return data


def main():
    data = build()
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(data, f, indent=2)
    n_bench = len(data["benchmarks"])
    print(f"wrote {OUT} ({n_bench} benchmark families, {data['task_count']} task rows)")


if __name__ == "__main__":
    main()
