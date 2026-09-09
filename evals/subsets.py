#!/usr/bin/env python3
"""Deterministic task-subset selection for the capability evaluation.

Every local subset is selected with a fixed seed (42) and stratified by a
metadata key (repo / language / category) so it is reproducible and never
cherry-picked. Only the selected task IDs are committed; the full upstream
datasets stay in .cache/evals/ or are fetched at runtime.

Selection rules:
  - Sort instances by a stable key, then round-robin across strata to
    spread the subset evenly, taking the first `size` chosen.
  - Deterministic given the same input list + seed.

Usage:
    python3 evals/subsets.py select --bench swe_verified \
        --instances <instances.json> --size 20 --stratify repo \
        --out evals/tasksets/swe_verified_local20.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKSETS = ROOT / "evals" / "tasksets"


def _stratum(inst, key):
    v = inst.get(key)
    if v is None:
        return "unknown"
    return str(v)


def select(instances, size, seed=42, stratify="repo", id_key="instance_id"):
    """Deterministic stratified selection. Returns list of instance dicts."""
    rng = random.Random(seed)
    # stable order
    ordered = sorted(instances, key=lambda i: str(i.get(id_key)))
    # group by stratum
    strata: dict[str, list] = {}
    for inst in ordered:
        strata.setdefault(_stratum(inst, stratify), []).append(inst)
    # within each stratum, deterministic shuffle with the seed
    for k in strata:
        lst = strata[k][:]
        rng.shuffle(lst)
        strata[k] = lst
    # round-robin across strata
    stratum_names = sorted(strata.keys())
    chosen: list[dict] = []
    while len(chosen) < size and any(strata.values()):
        progressed = False
        for k in stratum_names:
            if not strata[k]:
                continue
            if len(chosen) >= size:
                break
            chosen.append(strata[k].pop(0))
            progressed = True
        if not progressed:
            break
    chosen.sort(key=lambda i: str(i.get(id_key)))
    return chosen[:size]


def task_ids_hash(instances, id_key="instance_id"):
    """Reproducible hash over the selected task IDs (for manifest)."""
    ids = sorted(str(i.get(id_key)) for i in instances)
    return hashlib.sha256("\n".join(ids).encode()).hexdigest()


def load_json(path):
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        # accept {"instances": [...]} or {id: {...}}
        if "instances" in data:
            return data["instances"]
        return [{"instance_id": k, **v} for k, v in data.items()]
    return data


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("select")
    p.add_argument("--bench", required=True)
    p.add_argument("--instances", required=True, help="JSON list of instance dicts")
    p.add_argument("--size", type=int, required=True)
    p.add_argument("--stratify", default="repo")
    p.add_argument("--id-key", default="instance_id")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default=None)
    a = ap.parse_args()

    instances = load_json(a.instances)
    chosen = select(instances, a.size, a.seed, a.stratify, a.id_key)
    out = a.out or str(TASKSETS / f"{a.bench}_local{a.size}.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "benchmark": a.bench,
        "seed": a.seed,
        "stratify": a.stratify,
        "size": len(chosen),
        "task_ids_hash": task_ids_hash(chosen, a.id_key),
        "instance_ids": [i.get(a.id_key) for i in chosen],
    }
    with open(out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"selected {len(chosen)}/{len(instances)} -> {out} "
          f"(hash {payload['task_ids_hash'][:12]})")


if __name__ == "__main__":
    main()
