"""Smoke-test the registered Home Lab extension with the full-run GPU policy."""
import argparse
import json
import os
from pathlib import Path

from . import config, fresh, home


def inspect_failure(path, error):
    log = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    needles = ("out of memory", "failed to allocate", "cuda error", "unknown model architecture",
               "error loading model", "failed to load", "unsupported", "error:")
    evidence = [line.strip() for line in log.splitlines() if any(needle in line.lower() for needle in needles)]
    return {"error": str(error), "evidence": evidence[-6:]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=config.ROOT / ".agent/fresh-admission")
    parser.add_argument("--model", action="append", help="Restrict the smoke test to selected arms")
    args = parser.parse_args()
    models = config.models_for_cohort("home_refresh")
    if args.model:
        unknown = set(args.model) - {model["arm"] for model in models}
        if unknown:
            parser.error(f"unknown refresh arms: {', '.join(sorted(unknown))}")
        models = [model for model in models if model["arm"] in args.model]
    settings = json.loads(fresh.SETTINGS.read_text())
    tasks = {task["id"]: task for task in map(json.loads, fresh.TASKS.read_text().splitlines())}
    probes = [tasks[task] for task in settings["warmup_tasks"]]
    model_dir = Path(os.environ.get("MODEL_DIR", config.ROOT / "models")).resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    entries = []
    for model in models:
        arm = model["arm"]
        artifact = model_dir / model["gguf_filename"]
        settings["disable_reasoning_for"].append(arm)
        entry = {"arm": arm, "sha256": model["sha256"]}
        if not artifact.is_file() or home.sha(artifact) != model["sha256"]:
            entry.update(status="artifact_unavailable", error="Missing file or SHA-256 mismatch")
        else:
            try:
                rows, run = home.run_arm(model, probes, settings, args.output, model_dir)
                if any(row["status"] == "transport_error" or row["output_tokens"] is None for row in rows):
                    raise RuntimeError("Request did not finish with server-reported token usage")
                entry.update(status="admitted", peak_vram_mib=run["peak_vram_mib"],
                             offloaded_layers=run["offloaded_layers"], context_per_slot=run["context_per_slot"],
                             image_id=run["image_id"], replies=[row["status"] for row in rows])
            except RuntimeError as error:
                entry.update(status="failed", **inspect_failure(args.output / f"{arm}.server.log", error))
        entries.append(entry)
        print(f"{arm}: {entry['status']}", flush=True)
        fresh.save_json(args.output / "admission.json", entries)


if __name__ == "__main__":
    main()
