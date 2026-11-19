"""Run the expanded Home Lab corpus with resumable per-model checkpoints."""
import argparse
import csv
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import random
import subprocess

from . import config, home, home_report

ROOT = config.ROOT
SETTINGS = ROOT / "configs/fresh.json"
TASKS = ROOT / "configs/fresh_tasks.jsonl"
SOURCES = ROOT / "configs/fresh_sources.json"
PUBLISHED = ROOT / "results/current/fresh"


def atomic_text(path, data):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(data, encoding="utf-8", newline="\n")
    temp.replace(path)


def save_json(path, value):
    atomic_text(path, json.dumps(value, indent=2, ensure_ascii=True) + "\n")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".agent/fresh-run")
    args = parser.parse_args()
    settings = json.loads(SETTINGS.read_text())
    sources = json.loads(SOURCES.read_text())
    if sources["task_sha256"] != home.sha(TASKS):
        raise ValueError("task corpus does not match the frozen provenance")
    tasks = [json.loads(line) for line in TASKS.read_text().splitlines()]
    models = [model for cohort in settings["cohorts"] for model in config.models_for_cohort(cohort)]
    random.Random(settings["order_seed"]).shuffle(models)
    model_dir = Path(os.environ.get("MODEL_DIR", ROOT / "models")).resolve()
    plan = {
        "settings": settings, "settings_sha256": home.sha(SETTINGS), "tasks_sha256": home.sha(TASKS),
        "sources": sources, "runner_sha256": home.sha(Path(__file__)),
        "client_sha256": home.sha(Path(home.__file__)),
        "gpu": subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                                       "--format=csv,noheader,nounits"], text=True).strip(),
        "platform": os.uname().release, "order": [model["arm"] for model in models],
        "images": {}, "weights": {model["arm"]: model["sha256"] for model in models},
    }
    for engine in sorted({config.cohort_engine(model["cohort"]) for model in models}):
        image = config.engine_image(engine)
        plan["images"][image] = subprocess.check_output(
            ["docker", "image", "inspect", image, "--format", "{{.Id}}"], text=True).strip()
    args.output.mkdir(parents=True, exist_ok=True)
    plan_path = args.output / "plan.json"
    if plan_path.exists():
        previous = json.loads(plan_path.read_text())
        started = previous.pop("started_utc")
        if previous != plan:
            raise ValueError("saved run plan differs from this environment or configuration")
    else:
        if any(args.output.iterdir()):
            parser.error("output must be empty or contain a compatible run plan")
        started = utc_now()
        save_json(plan_path, plan | {"started_utc": started})

    for model in models:
        name = model["arm"]
        checkpoint = args.output / f"{name}.json"
        if checkpoint.exists():
            print(f"Reusing {name}", flush=True)
            continue
        file = model_dir / model["gguf_filename"]
        if not file.is_file() or home.sha(file) != model["sha256"]:
            raise ValueError(f"missing or invalid weight: {file.name}")
        print(f"Starting {name} at {utc_now()}", flush=True)
        rows, run = home.run_arm(model, tasks, settings, args.output, model_dir)
        if run["image_id"] != plan["images"][run["engine_image"]]:
            raise RuntimeError(f"image tag changed during {name}")
        save_json(checkpoint, {"run": run, "rows": rows})
    stream = io.StringIO()
    writer = csv.DictWriter(stream, home.COLUMNS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    arms = []
    for name in plan["order"]:
        checkpoint = json.loads((args.output / f"{name}.json").read_text())
        arms.append(checkpoint["run"])
        writer.writerows(checkpoint["rows"])
    atomic_text(args.output / "requests.tsv", stream.getvalue())
    (args.output / "tasks.jsonl").write_bytes(TASKS.read_bytes())
    save_json(args.output / "manifest.json", plan | {
        "started_utc": started, "finished_utc": utc_now(), "arms": arms,
    })
    home_report.read_run(args.output)


if __name__ == "__main__":
    main()

