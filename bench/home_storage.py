"""Compare warm-cache model startup from WSL and Windows-mounted storage."""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from . import config
from .home import SETTINGS, TASKS, request_task, sha, wait_server
from .serving import start_server


def launch(path, label, repeat, model, image, settings, flags):
    name = f"home-storage-{os.getpid()}"
    url = f"http://127.0.0.1:{model['port']}"
    start = time.perf_counter()
    try:
        result = start_server(name, image, model["port"], model["gguf_filename"],
                              model["arm"], path, flags)
        if result.returncode:
            raise RuntimeError(result.stderr.strip())
        wait_server(url, name)
        ready = (time.perf_counter() - start) * 1000
        task = json.loads(TASKS.read_text(encoding="utf-8").splitlines()[0])
        result = request_task(url, model["arm"], task, settings)
        if result["status"] == "transport_error" or result["first_answer_ms"] is None:
            raise RuntimeError("startup probe received no visible answer")
        return {
            "storage": label, "repeat": repeat, "ready_ms": ready,
            "first_answer_ms": result["first_answer_ms"], "finished_ms": result["complete_ms"],
        }
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("linux_dir", type=Path)
    parser.add_argument("windows_dir", type=Path)
    args = parser.parse_args()
    paths = {"linux": args.linux_dir.resolve(), "windows_mount": args.windows_dir.resolve()}
    model = config.model_by_arm("phi4_mini_compact")
    fs = {}
    for label, directory in paths.items():
        # Pre-read both identical files so this is a warm-cache launch comparison.
        if sha(directory / model["gguf_filename"]) != model["sha256"]:
            parser.error(f"{label} weight checksum mismatch")
        fs[label] = subprocess.check_output(
            ["findmnt", "-n", "-o", "FSTYPE", "-T", str(directory)], text=True).strip()
    if len(set(fs.values())) != 2:
        parser.error("use a Linux path and a Windows-mounted path on different filesystems")
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    image = config.engine_image(config.cohort_engine(model["cohort"]))
    flags = ["--ctx-size", str(settings["context"]), "--parallel", str(settings["slots"]),
             "--cont-batching", "--metrics", "--n-gpu-layers", str(settings["gpu_layers"])]
    rows = []
    for repeat, order in enumerate((("linux", "windows_mount"), ("windows_mount", "linux"),
                                    ("linux", "windows_mount")), start=1):
        for label in order:
            rows.append(launch(paths[label], label, repeat, model, image, settings, flags))
    print(json.dumps({
        "model": model["display_name"], "gguf_sha256": model["sha256"], "engine_image": image,
        "platform": os.uname().release, "flags": flags, "filesystems": fs, "repeats": rows,
    }, indent=2))


if __name__ == "__main__":
    main()
