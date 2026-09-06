"""llama-bench microbenchmark for the active cohort.

Runs the pinned upstream llama.cpp `llama-bench` binary (same image used for
serving) against each enabled 8-9B GGUF. Output is kept separate from the
AIPerf end-to-end serving numbers: llama-bench measures raw engine token
throughput (pp512 prompt processing, tg128 token generation), not the served
API latency/throughput path.
"""
import os
import subprocess
import sys
from pathlib import Path

from . import config

IMAGE = os.environ.get("LLAMA_UPSTREAM_IMAGE", "llama-cpp-upstream:v0.4.0")
MODEL_DIR = os.environ.get("MODEL_DIR", str(config.ROOT / "models"))
OUT = config.ROOT / "results" / "current" / "llama-bench"

# Fixed microbenchmark geometry, identical across models.
PROMPT_TOKENS = "512"
GEN_TOKENS = "128"
REPS = "3"
NGL = "99"


def main():
    arms = [m for m in config.models()
            if m.get("cohort") == "mainstream_8_9b" and m.get("enabled")]
    if not arms:
        print("no enabled mainstream_8_9b models")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for m in arms:
        gguf = m["gguf_filename"]
        dst = OUT / (m["id"] + ".txt")
        cmd = ["docker", "run", "--rm", "--gpus", "all", "--ipc", "host",
               "-v", f"{MODEL_DIR}:/models:ro",
               "--entrypoint", "/src/build/bin/llama-bench", IMAGE,
               "-m", f"/models/{gguf}",
               "-p", PROMPT_TOKENS, "-n", GEN_TOKENS, "-r", REPS, "-ngl", NGL]
        print(f"[{m['id']}] llama-bench -> {dst}", flush=True)
        with open(dst, "w") as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
