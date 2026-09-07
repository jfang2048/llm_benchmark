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


def models():
    """Return the list of registered models."""
    return load_models()["models"]


def cohorts():
    """Return the cohort definitions keyed by cohort name."""
    return load_models()["cohorts"]


def primary_cohort():
    """Return the models that form the current primary benchmark cohort."""
    return [m for m in models() if m.get("primary")]


def models_for_cohort(cohort):
    """Return enabled models in a given cohort, in registry order."""
    return [m for m in models()
            if m.get("cohort") == cohort and m.get("enabled")]


def reference_models():
    """Return first-class reference models (cross-cohort baselines)."""
    return [m for m in models() if m.get("role") == "reference" and m.get("enabled")]


def visible_models():
    """Return models shown in the current dashboard (primary + reference)."""
    return [m for m in models() if m.get("enabled") and m.get("cohort") in
            ("mainstream_8_9b", "spark_reference")]


def engines():
    """Return the engine registry {name: {source, commit, image, ...}}."""
    return load_models().get("engines", {})


def cohort_engine(cohort):
    """Return the engine name for a cohort, or None."""
    return cohorts().get(cohort, {}).get("engine")


def engine_image(engine):
    """Return the Docker image for an engine name, or None."""
    return engines().get(engine, {}).get("image")


def enabled_models():
    """Return models enabled for benchmarking (passed admission)."""
    return [m for m in models() if m.get("enabled")]


def model_by_arm(arm):
    """Return the model dict for an arm key, or None."""
    for m in models():
        if m.get("arm") == arm:
            return m
    return None


def reliability_min_success():
    """Return the transport-reliability gate threshold (percent)."""
    return float(load_benchmark()["reliability"]["min_success_pct"])
