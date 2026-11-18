"""Read and summarize a complete Home Lab run without model or GPU dependencies."""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from .config import ROOT
from .stats import percentile

PUBLISHED = ROOT / "results/current/home-lab"
STATUSES = {"correct", "invalid_json", "wrong_value", "truncated", "no_answer", "transport_error"}


def number(value):
    if value is None or value == "":
        return None
    n = float(value)
    if not math.isfinite(n) or n < 0:
        raise ValueError(f"invalid measurement: {value}")
    return n


def timely(row, budget):
    answer = number(row["first_answer_ms"])
    complete = number(row["complete_ms"])
    return (row["status"] == "correct" and answer is not None and complete is not None
            and answer <= budget["first_answer_ms"] and complete <= budget["complete_ms"])


def counts(rows, budget):
    return {"n": len(rows), "correct": sum(r["status"] == "correct" for r in rows),
            "timely": sum(timely(r, budget) for r in rows)}


def read_run(path):
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    task_bytes = (path / "tasks.jsonl").read_bytes()
    if hashlib.sha256(task_bytes).hexdigest() != manifest["tasks_sha256"]:
        raise ValueError("task corpus checksum mismatch")
    tasks = [json.loads(line) for line in task_bytes.decode("utf-8").splitlines()]
    task_ids = {task["id"]: (task["kind"], task["language"]) for task in tasks}
    arms = {arm["arm"] for arm in manifest["arms"]}
    settings = manifest["settings"]
    repeats = set(range(1, settings["repeats"] + 1))
    scenarios = set(settings["scenarios"])
    if not arms or len(tasks) != len(task_ids) or len(arms) != len(manifest["arms"]):
        raise ValueError("empty run or duplicate task or arm")
    cells = {(arm, scenario, repeat) for arm in arms for scenario in scenarios for repeat in repeats}
    groups = defaultdict(list)
    seen = set()
    with (path / "requests.tsv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            cell = row["arm"], row["scenario"], int(row["repeat"])
            key = (*cell, row["task"])
            if (key in seen or cell not in cells or row["status"] not in STATUSES or
                    task_ids.get(row["task"]) != (row["kind"], row["language"]) or
                    row["fence_correct"] not in ("0", "1") or
                    (row["fence_correct"] == "1" and row["status"] != "invalid_json") or
                    row["redaction_leak"] not in ("", "0", "1") or
                    (row["kind"] != "redact" and row["redaction_leak"] != "")):
                raise ValueError(f"unexpected or duplicate request row: {key}")
            end = number(row["complete_ms"])
            first = number(row["first_token_ms"])
            visible = number(row["first_answer_ms"])
            if (end is None or (first is not None and first > end) or
                    (visible is not None and (first is None or visible < first or visible > end)) or
                    (row["status"] == "correct" and visible is None)):
                raise ValueError(f"inconsistent clocks: {key}")
            number(row["input_tokens"])
            number(row["output_tokens"])
            groups[cell[:2]].append(row)
            seen.add(key)
    if len(seen) != len(cells) * len(tasks):
        raise ValueError("incomplete Home Lab run")
    for model in manifest["arms"]:
        windows = model["windows"]
        window_ids = {(w["scenario"], w["repeat"]) for w in windows}
        expected = {(scenario, repeat) for scenario in scenarios for repeat in repeats}
        if (window_ids != expected or len(windows) != len(expected) or
                any(not number(w["seconds"]) for w in windows)):
            raise ValueError(f"missing or invalid time window: {model['arm']}")
    return manifest, groups, task_ids


def summarize_scenario(rows, budget, seconds):
    tally = counts(rows, budget)
    failures = Counter(r["status"] for r in rows if r["status"] != "correct")
    correct_rows = [r for r in rows if r["status"] == "correct"]
    redaction_outputs = [r for r in rows if r["redaction_leak"] in ("0", "1")]
    tokens = [number(r["output_tokens"]) for r in rows]
    summary = {
        **tally, "failures": dict(sorted(failures.items())),
        "redaction_outputs": len(redaction_outputs),
        "redaction_leaks": sum(r["redaction_leak"] == "1" for r in redaction_outputs),
        "goodput_per_min": 60 * tally["timely"] / seconds,
        "output_tok_per_s": sum(tokens) / seconds if all(n is not None for n in tokens) else None,
    }
    for field in ("kind", "language"):
        summary[f"by_{field}"] = {
            value: counts([r for r in rows if r[field] == value], budget)
            for value in sorted({r[field] for r in rows})
        }
    for out, field in (("answer", "first_answer_ms"), ("complete", "complete_ms"),
                       ("token", "first_token_ms")):
        values = [v for r in correct_rows if (v := number(r[field])) is not None]
        for p in (50, 95):
            summary[f"{out}_p{p}_ms"] = percentile(values, p)
    return summary


def storage_summary(path):
    if not path.exists():
        return None
    probe = json.loads(path.read_text(encoding="utf-8"))
    data = {}
    for kind in ("linux", "windows_mount"):
        rows = [r for r in probe["repeats"] if r["storage"] == kind]
        if sorted(r["repeat"] for r in rows) != [1, 2, 3]:
            raise ValueError(f"incomplete storage sample: {kind}")
        ready = [number(r["ready_ms"]) for r in rows]
        finish = [number(r["finished_ms"]) for r in rows]
        if any(v is None or v <= 0 for v in ready + finish):
            raise ValueError(f"invalid storage time: {kind}")
        data[kind] = {"ready_ms": percentile(ready, 50), "finished_ms": percentile(finish, 50)}
    return data


def load_fit(path, manifest):
    if not path.exists():
        return None
    fit = json.loads(path.read_text(encoding="utf-8"))
    if any(fit[key] != manifest[key] for key in ("gpu", "platform")):
        raise ValueError("context probe used a different GPU environment")
    if fit["auto_fit"] or fit["slots"] != manifest["settings"]["slots"] or fit["gpu_layers"] != 999:
        raise ValueError("context probe must request full offload with the same slot count")
    contexts = fit["contexts"]
    fit["vram_total_mib"] = number(fit["gpu"].rsplit(",", 2)[1])
    if not fit["vram_total_mib"] or not contexts:
        raise ValueError("missing device VRAM or context points")
    names = {m["arm"]: m["name"] for m in manifest["arms"]}
    seen = set()
    for row in fit["rows"]:
        key = row["arm"], row["context"]
        if key in seen or row["arm"] not in names or row["context"] not in contexts:
            raise ValueError(f"unexpected context row: {key}")
        seen.add(key)
        row["name"] = names[row["arm"]]
        row["peak_vram_mib"] = number(row["peak_vram_mib"])
        row["fully_offloaded"] = (
            row["status"] == "streamed" and row["offloaded_layers"] is not None
            and row["offloaded_layers"] == row["total_layers"]
            and row["per_slot_context"] == row["context"] // fit["slots"]
        )
    if not seen or len(seen) != len({arm for arm, _ in seen}) * len(contexts):
        raise ValueError("incomplete context matrix")
    return fit


def summarize(path):
    manifest, groups, task_ids = read_run(path)
    settings = manifest["settings"]
    models = []
    for model in manifest["arms"]:
        scenarios = {}
        for scenario, budget in settings["scenarios"].items():
            rows = groups[model["arm"], scenario]
            seconds = sum(w["seconds"] for w in model["windows"] if w["scenario"] == scenario)
            wrapped = [dict(row, status="correct") if row["fence_correct"] == "1" else row for row in rows]
            scenarios[scenario] = {
                **summarize_scenario(rows, budget, seconds),
                "with_fence": summarize_scenario(wrapped, budget, seconds),
            }
        metadata = {k: model[k] for k in ("arm", "name", "cohort", "quantization", "engine_image",
                                         "startup_ms", "peak_vram_mib")}
        models.append(dict(metadata, scenarios=scenarios))
    return {
        "scenarios": settings["scenarios"], "models": models, "cases": len(task_ids),
        "repeats": settings["repeats"], "gpu": manifest["gpu"], "platform": manifest["platform"],
        "slots": settings["slots"], "context": settings["context"],
        "storage": storage_summary(path / "storage.json"),
        "fit": load_fit(path / "fit.json", manifest),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, nargs="?", default=PUBLISHED)
    args = parser.parse_args()
    print(json.dumps(summarize(args.run), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
