"""Canonical configuration loader.

Single source of truth for benchmark and model configuration:
configs/benchmark.json and configs/models.json. Consumed by the runner,
the report generator, and CI validation so they cannot drift.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_benchmark():
    """Return the benchmark config dict (shape profiles, concurrency, ...)."""
    return json.loads((ROOT / "configs" / "benchmark.json").read_text(encoding="utf-8"))


def load_models():
    """Return the model registry dict."""
    return json.loads((ROOT / "configs" / "models.json").read_text(encoding="utf-8"))


def shape_profiles():
    """Return {profile_name: (isl, osl)} from the canonical benchmark config."""
    sp = load_benchmark()["shape_profiles"]
    return {name: (p["isl"], p["osl"]) for name, p in sp["profiles"].items()}


def shape_order():
    """Return the ordered list of shape profile names."""
    return load_benchmark()["shape_profiles"]["order"]


def reliability_min_success():
    """Return the transport-reliability gate threshold (percent)."""
    return float(load_benchmark()["reliability"]["min_success_pct"])
