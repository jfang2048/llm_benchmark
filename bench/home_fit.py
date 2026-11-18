"""Measure CUDA offload and VRAM at several context sizes."""
import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from . import config, results
from .home import SETTINGS, TASKS, request_task, sha, wait_server
from .serving import Telemetry, gpu_vram, start_server, wait_for_temperature

OFFLOAD = re.compile(r"offloaded\s+(\d+)\s*/\s*(\d+)\s+layers to GPU", re.IGNORECASE)
SLOTS = re.compile(r"n_ctx_slot\s*=\s*(\d+)")


def probe(model, model_dir, context, settings, log_dir):
    arm = model["arm"]
    name = f"home-fit-{os.getpid()}"
    image = config.engine_image(config.cohort_engine(model["cohort"]))
    flags = ["--ctx-size", str(context), "--parallel", str(settings["slots"]), "--cont-batching",
             "--n-gpu-layers", "999", "--fit", "off", "-lv", "4"]
    if arm in settings["disable_reasoning_for"]:
        flags += ["--reasoning", "off"]
    url = f"http://127.0.0.1:{model['port']}"
    stats_file = log_dir / f"{arm}-{context}.csv"
    telemetry = Telemetry(stats_file)
    ready, outcome = None, "startup_failed"
    baseline = None
    try:
        wait_for_temperature(70)
        baseline = gpu_vram()
        launched = start_server(name, image, model["port"], model["gguf_filename"], arm, model_dir, flags)
        if launched.returncode == 0:
            telemetry.start()
            try:
                wait_server(url, name, deadline=45)
            except RuntimeError:
                pass
            else:
                ready = gpu_vram()
                task = json.loads(TASKS.read_text(encoding="utf-8").splitlines()[0])
                row = request_task(url, arm, task, settings)
                outcome = "streamed" if row["finish_reason"] and row["first_token_ms"] is not None else "stream_failed"
        log = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
    finally:
        telemetry.stop()
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)

    detail = log.stdout + log.stderr
    (log_dir / f"{arm}-{context}.log").write_text(detail, encoding="utf-8")
    offload = OFFLOAD.search(detail)
    slot = SLOTS.search(detail)
    peak, *_ = results.parse_gpu_csv(stats_file)
    gpu = [v for v in (ready, peak) if v is not None]
    return {
        "arm": arm, "context": context, "per_slot_context": int(slot[1]) if slot else None,
        "offloaded_layers": int(offload[1]) if offload else None,
        "total_layers": int(offload[2]) if offload else None,
        "baseline_vram_mib": baseline, "peak_vram_mib": max(gpu) if gpu else None, "status": outcome,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", action="append", required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output file already exists")
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    model_dir = Path(os.environ.get("MODEL_DIR", config.ROOT / "models")).resolve()
    models = []
    for arm in dict.fromkeys(args.model):
        model = config.model_by_arm(arm)
        if model is None or config.cohort_engine(model["cohort"]) != "upstream_llama_cpp":
            parser.error(f"unknown or unsupported model: {arm}")
        if sha(model_dir / model["gguf_filename"]) != model["sha256"]:
            parser.error(f"invalid checksum: {arm}")
        models.append(model)
    contexts = (4096, 8192, 16384)
    gpu = subprocess.check_output(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                                   "--format=csv,noheader,nounits"], text=True).strip()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    log_dir = Path(tempfile.mkdtemp(prefix="fit-", dir=args.out.parent))
    rows = []
    for model in models:
        for context in contexts:
            row = probe(model, model_dir, context, settings, log_dir)
            print(row, flush=True)
            rows.append(row)
    data = {"gpu": gpu, "platform": os.uname().release, "slots": settings["slots"],
            "contexts": contexts, "gpu_layers": 999, "auto_fit": False, "rows": rows}
    args.out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
