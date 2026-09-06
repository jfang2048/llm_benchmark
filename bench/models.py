"""Model registry access.

Thin wrapper over bench.config that answers deployment questions: which arms
form the active benchmark cohort, and how each is served (port, container,
GGUF, chat-template policy). Kept here so the runner and report generator
derive model lists from the registry instead of hardcoding names.
"""
from . import config


def primary_arms():
    """Return arm keys of the current primary cohort, in registry order."""
    return [m["arm"] for m in config.primary_cohort()]


def enabled_arms():
    """Return arm keys of models that passed admission (enabled=true)."""
    return [m["arm"] for m in config.enabled_models()]


def arm_config():
    """Return {arm: {url, container, model, gguf, chat_template, quantization}}.

    The container name convention is `bench-<arm>` with underscores mapped to
    hyphens, matching the historical `bench-spark-llama` / `bench-qwen-llama`
    naming.
    """
    out = {}
    for m in config.models():
        arm = m["arm"]
        out[arm] = {
            "display_name": m["display_name"],
            "url": f"http://127.0.0.1:{m['port']}",
            "container": "bench-" + arm.replace("_", "-"),
            "model": m["gguf_filename"].removesuffix(".gguf"),
            "gguf": m["gguf_filename"],
            "chat_template": m["chat_template"],
            "quantization": m["quantization"],
            "actual_parameter_count": m.get("actual_parameter_count"),
            "cohort": m["cohort"],
        }
    return out


def model_by_arm(arm):
    """Return the model dict for an arm key, or None."""
    for m in config.models():
        if m.get("arm") == arm:
            return m
    return None
