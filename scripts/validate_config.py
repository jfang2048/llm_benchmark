#!/usr/bin/env python3
"""Validate the canonical benchmark/model configuration.

Ensures the single source of truth (configs/models.json + configs/benchmark.json)
is internally consistent and that committed result metadata only references
workload profiles defined by that configuration. Fails (exit non-zero) on any
violation so CI rejects drift between the runner and the published data.

Usage:
    python3 scripts/validate_config.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "configs" / "models.json"
BENCHMARK = ROOT / "configs" / "benchmark.json"
FINAL = ROOT / "results" / "v2" / "final"

errors = []


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        errors.append(f"{path}: invalid JSON: {e}")
        return None


def main():
    models = load(MODELS)
    bench = load(BENCHMARK)

    if models is not None:
        ids = [m.get("id") for m in models.get("models", [])]
        if len(ids) != len(set(ids)):
            errors.append("models.json: duplicate model ids")
        for m in models.get("models", []):
            for req in ("id", "display_name", "arm", "quantization", "sha256"):
                if not m.get(req):
                    errors.append(f"models.json: model {m.get('id')} missing '{req}'")

    if bench is not None:
        sp = bench.get("shape_profiles", {})
        order = sp.get("order", [])
        profiles = sp.get("profiles", {})
        if sorted(order) != sorted(profiles.keys()):
            errors.append("benchmark.json: shape_profiles.order does not match profiles keys")
        for name, p in profiles.items():
            if not isinstance(p.get("isl"), int) or not isinstance(p.get("osl"), int):
                errors.append(f"benchmark.json: profile '{name}' missing integer isl/osl")

    # Committed result metadata must not reference an undefined shape profile.
    defined = set()
    if bench is not None:
        defined = set(bench.get("shape_profiles", {}).get("profiles", {}).keys())
    for tsv in sorted(FINAL.glob("*/aggregate.tsv")) + sorted(FINAL.glob("*/repeats.tsv")):
        try:
            import csv
            rows = list(csv.DictReader(open(tsv, encoding="utf-8"), delimiter="\t"))
        except Exception as e:
            errors.append(f"{tsv.relative_to(ROOT)}: cannot read: {e}")
            continue
        for r in rows:
            suite = r.get("suite", "")
            if suite.startswith("shape_"):
                profile = suite[len("shape_"):]
                if profile and profile not in defined:
                    errors.append(
                        f"{tsv.relative_to(ROOT)}: suite '{suite}' references undefined "
                        f"shape profile '{profile}'"
                    )

    if errors:
        print("config validation FAILED:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    print("config validation PASSED")
    print(f"  models: {len(models['models']) if models else 0} primary")
    print(f"  shape profiles: {', '.join(defined)}")


if __name__ == "__main__":
    main()
