"""Validate and summarize the published single-factor comparisons."""
import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from statistics import median

from . import config, home
from .controlled import ARMS, schedule, validate_design
from .stats import percentile

PUBLISHED = config.ROOT / "results/current/controlled"
METRICS = {
    "correct": ("Correct replies", "replies"),
    "on_time": ("Correct and on time", "replies"),
    "first_ms": ("First visible answer p95", "ms"),
    "complete_ms": ("End-to-end p95", "ms"),
    "goodput": ("Usable jobs per minute", "jobs/min"),
    "output_tps": ("Aggregate output throughput", "tokens/s"),
    "peak_mib": ("Sampled peak VRAM", "MiB"),
    "delta_mib": ("Peak above pre-launch VRAM", "MiB"),
}


def run_metrics(rows, run, design):
    finished = [row for row in rows if row["status"] != "transport_error"]
    visible = [float(row["first_answer_ms"]) for row in finished if row["first_answer_ms"]]
    correct = [row for row in finished if row["status"] == "correct"]
    on_time = sum(bool(row["first_answer_ms"])
                  and float(row["first_answer_ms"]) <= design["first_answer_ms"]
                  and float(row["complete_ms"]) <= design["complete_ms"] for row in correct)
    seconds = run["seconds"]
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("invalid measured window")
    return {
        "correct": len(correct),
        "on_time": on_time,
        "first_ms": percentile(visible, 95),
        "complete_ms": percentile([row["complete_ms"] for row in finished], 95),
        "goodput": on_time * 60 / seconds,
        "output_tps": (sum(int(row["output_tokens"]) for row in finished) / seconds
                       if finished and all(row["output_tokens"] for row in finished) else None),
        "peak_mib": run["peak_vram_mib"],
        "delta_mib": run["peak_vram_mib"] - run["before_launch_vram_mib"],
    }


def paired_values(pairs, metric):
    values = [(pair["baseline"][metric], pair["changed"][metric]) for pair in pairs]
    deltas = [b - a for a, b in values if a is not None and b is not None]
    medians = {}
    for index, arm in enumerate(ARMS):
        measured = [value[index] for value in values if value[index] is not None]
        medians[arm] = round(median(measured), 2) if measured else None
    return medians | {
        "median_delta": round(median(deltas), 2) if deltas else None,
        "min_delta": round(min(deltas), 2) if deltas else None,
        "max_delta": round(max(deltas), 2) if deltas else None,
        "pairs": len(deltas),
    }


def summarize(directory):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    design = manifest["design"]
    validate_design(design, manifest["models"])
    task_path = directory / "tasks.jsonl"
    if home.sha(task_path) != manifest["tasks_sha256"]:
        raise ValueError("fixture checksum mismatch")
    tasks = [json.loads(line) for line in task_path.read_text(encoding="utf-8").splitlines()]
    key = lambda record: (record["experiment"], int(record["pair"]), record["arm"])
    rows = defaultdict(list)
    with (directory / "requests.tsv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            rows[key(row)].append(row)
    runs = {key(run): run for run in manifest["runs"]}
    expected_runs = [(experiment["id"], pair, side)
                     for pair in range(1, design["pairs"] + 1)
                     for experiment in design["experiments"]
                     for side in schedule(pair)]
    if [key(run) for run in manifest["runs"]] != expected_runs or set(rows) != set(expected_runs):
        raise ValueError("missing, duplicate or out-of-order runs")

    for experiment_id, pair, side in expected_runs:
        run = runs[experiment_id, pair, side]
        if run["prompt_prefixes_checked"] != len(tasks) + len(manifest["warmup_tasks"]):
            raise ValueError(f"{experiment_id}/{pair}/{side}: incomplete prompt cache audit")
        if run["offloaded_layers"] <= 0 or run["start_temperature_c"] > design["max_start_temperature_c"]:
            raise ValueError(f"{experiment_id}/{pair}/{side}: launch checks failed")

    experiments = []
    for experiment in design["experiments"]:
        pairs = []
        for number in range(1, design["pairs"] + 1):
            order = schedule(number)
            expected = random.Random(design["seed"] + number).sample(tasks, len(tasks))
            values = {}
            for position, side in enumerate(order, 1):
                run_key = (experiment["id"], number, side)
                run = runs[run_key]
                settings = experiment[side]
                if run["context_per_slot"] != settings["context"] // design["slots"]:
                    raise ValueError(f"{run_key}: context per slot differs from plan")
                records = rows[run_key]
                if run["position"] != position or any(int(row["position"]) != position for row in records):
                    raise ValueError(f"{run_key}: incorrect launch order")
                fields = ("id", "kind", "language")
                actual = [(row["task"], row["kind"], row["language"]) for row in records]
                if actual != [tuple(task[field] for field in fields) for task in expected]:
                    raise ValueError(f"{run_key}: missing, duplicate or out-of-order requests")
                values[side] = run_metrics(records, run, design)
                values[side]["transport_errors"] = sum(row["status"] == "transport_error" for row in records)
            pairs.append({"number": number, "order": order, **values})
        experiments.append(experiment | {
            "pairs": pairs,
            "summary": {metric: paired_values(pairs, metric) for metric in METRICS},
        })
    return {
        "gpu": manifest["gpu"], "kernel": manifest["kernel"], "pair_count": design["pairs"],
        "request_count": sum(map(len, rows.values())), "metrics": METRICS,
        "task_count": len(tasks), "weight_labels": {name: model["display_name"]
                                                   for name, model in manifest["models"].items()},
        "transport_errors": sum(row["status"] == "transport_error" for group in rows.values() for row in group),
        "experiments": experiments,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?", default=PUBLISHED)
    args = parser.parse_args()
    print(json.dumps(summarize(args.directory), indent=2, ensure_ascii=False))
