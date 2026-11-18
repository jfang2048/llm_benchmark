"""Run interleaved, single-factor Home Lab comparisons on one GPU."""
import argparse
import csv
import json
import os
import random
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import config, home, results
from .home_fit import OFFLOAD, SLOTS
from .serving import Telemetry, gpu_metric, gpu_vram, start_server, wait_for_temperature

DESIGN = config.ROOT / "configs/controlled.json"
DIMENSIONS = {"model", "engine", "context", "clients"}
ARMS = ("baseline", "changed")
PORT = 8242


def validate_design(design, models):
    if design["pairs"] < 2 or design["pairs"] % 2:
        raise ValueError("an even number of pairs is required for a balanced launch order")
    ids = [experiment["id"] for experiment in design["experiments"]]
    if len(ids) != len(set(ids)):
        raise ValueError("experiment IDs must be unique")
    for experiment in design["experiments"]:
        a, b = (experiment[arm] for arm in ARMS)
        difference = {key for key in DIMENSIONS if a.get(key) != b.get(key)}
        if a.keys() != DIMENSIONS or b.keys() != DIMENSIONS or difference != {experiment["factor"]}:
            raise ValueError(f"{experiment['id']}: expected exactly one changed setting")
        for arm in (a, b):
            if arm["model"] not in models or not config.engine_image(arm["engine"]):
                raise ValueError(f"{experiment['id']}: unknown model or engine")
            if arm["clients"] <= 0 or arm["context"] % design["slots"]:
                raise ValueError(f"{experiment['id']}: invalid load or unequal context split")
        if experiment["factor"] == "model":
            left, right = models[a["model"]], models[b["model"]]
            if left["quantization"] != right["quantization"]:
                raise ValueError(f"{experiment['id']}: model sizes must use the same quantization")


def schedule(pair):
    # Every experiment starts A first three times and B first three times.
    return ARMS if pair % 2 else ARMS[::-1]


def run_arm(arm, design, ordered, warmups, model, model_dir, image_id, output, run_id):
    name = f"controlled-{os.getpid()}"
    url = f"http://127.0.0.1:{PORT}"
    flags = [
        "--ctx-size", str(arm["context"]), "--parallel", str(design["slots"]),
        "--fit", "off", "--n-gpu-layers", "999", "--cont-batching",
        "--reasoning", "off", "--cache-type-k", "f16", "--cache-type-v", "f16",
        "--cache-ram", "0", "-lv", "4",
    ]
    temperature_limit = design["max_start_temperature_c"]
    if not wait_for_temperature(temperature_limit):
        raise RuntimeError(f"GPU failed to cool to {temperature_limit} C")
    start_temp = gpu_metric("temperature.gpu")
    external_vram = gpu_vram()
    telemetry = Telemetry(output / f"{run_id}.gpu.csv")
    started = time.perf_counter()
    try:
        launch = start_server(name, image_id, PORT, model["gguf_filename"], "controlled", model_dir, flags)
        if launch.returncode:
            raise RuntimeError(launch.stderr.strip())
        home.wait_server(url, name)
        startup_ms = (time.perf_counter() - started) * 1000
        ready_vram = gpu_vram()
        telemetry.start()
        for task in warmups:
            if home.request_task(url, "controlled", task, design)["status"] == "transport_error":
                raise RuntimeError(f"{run_id}: warmup request failed")
        with ThreadPoolExecutor(max_workers=arm["clients"]) as pool:
            start = time.perf_counter()
            rows = list(pool.map(lambda task: home.request_task(url, "controlled", task, design), ordered))
            elapsed = time.perf_counter() - start
        telemetry.stop()
        peak, _, _, peak_temperature, _ = results.parse_gpu_csv(telemetry.path)
        log = subprocess.run(["docker", "logs", name], capture_output=True, text=True, check=True)
        startup_log = log.stdout + log.stderr
        offload = OFFLOAD.findall(startup_log)
        slots = {int(value) for value in SLOTS.findall(startup_log)}
        expected_context = arm["context"] // design["slots"]
        if not offload or offload[-1][0] != offload[-1][1] or slots != {expected_context}:
            raise RuntimeError(f"{run_id}: full offload or requested context could not be verified")
        if "prompt cache is disabled" not in startup_log.lower():
            raise RuntimeError(f"{run_id}: server-side prompt cache could not be verified")
        # Later chunks of the same prompt reuse their own in-request KV state.
        prefixes = {}
        for task_id, cached in re.findall(r"task (\d+) \| cached n_tokens = (\d+)", startup_log):
            prefixes.setdefault(task_id, int(cached))
        if len(prefixes) != len(ordered) + len(warmups) or any(prefixes.values()):
            raise RuntimeError(f"{run_id}: unexpected prompt reuse")
        if any(word in startup_log.lower() for word in ("out of memory", "cuda error", "failed to allocate")):
            raise RuntimeError(f"{run_id}: allocation error")
        if None in (start_temp, external_vram, ready_vram, peak, peak_temperature):
            raise RuntimeError(f"{run_id}: GPU telemetry missing")
        return rows, {
            "flags": flags, "startup_ms": startup_ms, "start_temperature_c": start_temp,
            "peak_temperature_c": peak_temperature, "before_launch_vram_mib": external_vram,
            "ready_vram_mib": ready_vram, "peak_vram_mib": max(ready_vram, peak), "seconds": elapsed,
            "offloaded_layers": int(offload[-1][0]), "context_per_slot": expected_context,
            "prompt_prefixes_checked": len(prefixes),
        }
    finally:
        telemetry.stop()
        log = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
        (output / f"{run_id}.server.log").write_text(log.stdout + log.stderr, encoding="utf-8")
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=config.ROOT / ".agent/controlled")
    args = parser.parse_args()
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    models = {model["id"]: model for model in config.enabled_models()}
    validate_design(design, models)
    tasks = [json.loads(line) for line in home.TASKS.read_text(encoding="utf-8").splitlines()]
    warmups = [tasks[0], next(task for task in tasks if task.get("archive"))]
    model_dir = Path(os.environ.get("MODEL_DIR", config.ROOT / "models")).resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error("output directory must be empty")

    used = [experiment[arm] for experiment in design["experiments"] for arm in ARMS]
    weights, engines = {}, {}
    for model_id in sorted({arm["model"] for arm in used}):
        model = models[model_id]
        file = model_dir / model["gguf_filename"]
        if not file.is_file() or home.sha(file) != model["sha256"]:
            parser.error(f"missing or invalid weight checksum: {file.name}")
        weights[model_id] = {key: model[key] for key in
                             ("display_name", "quantization", "sha256", "gguf_source", "gguf_filename")}
    for engine in sorted({arm["engine"] for arm in used}):
        image = config.engine_image(engine)
        engines[engine] = config.engines()[engine] | {
            "image_id": subprocess.check_output(["docker", "image", "inspect", image,
                                                 "--format", "{{.Id}}"], text=True).strip()
        }

    manifest = {
        "design": design, "design_sha256": home.sha(DESIGN), "tasks_sha256": home.sha(home.TASKS),
        "runner_sha256": home.sha(Path(__file__)), "client_sha256": home.sha(Path(home.__file__)),
        "started_utc": datetime.now(timezone.utc).isoformat(), "kernel": os.uname().release,
        "gpu": subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                                       "--format=csv,noheader,nounits"], text=True).strip(),
        "models": weights, "engines": engines, "warmup_tasks": [task["id"] for task in warmups],
        "runs": [],
    }
    columns = ["experiment", "pair", "arm", "position"] + home.COLUMNS[3:]
    with (args.output / "requests.tsv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for pair in range(1, design["pairs"] + 1):
            ordered = random.Random(design["seed"] + pair).sample(tasks, len(tasks))
            for experiment in design["experiments"]:
                for position, side in enumerate(schedule(pair), 1):
                    arm = experiment[side]
                    tag = f"{experiment['id']}-{pair}-{side}"
                    print(f"{tag}: {arm}", flush=True)
                    rows, metadata = run_arm(arm, design, ordered, warmups, models[arm["model"]],
                                             model_dir, engines[arm["engine"]]["image_id"],
                                             args.output, tag)
                    common = dict(experiment=experiment["id"], pair=pair, arm=side, position=position)
                    for task, row in zip(ordered, rows, strict=True):
                        writer.writerow(dict(common, **row, task=task["id"], kind=task["kind"],
                                             language=task["language"]))
                    stream.flush()
                    manifest["runs"].append(common | metadata)
                    print(f"  {sum(row['status'] == 'correct' for row in rows)}/{len(rows)} correct"
                          f" in {metadata['seconds']:.2f}s, {metadata['peak_vram_mib']} MiB", flush=True)
    manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
    (args.output / "tasks.jsonl").write_bytes(home.TASKS.read_bytes())
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

