"""Capacity benchmark runner for the active primary cohort.

Registry-driven: the arm list, ports, containers, GGUFs and chat templates come
from configs/models.json via bench.config/bench.models; the sweep parameters
come from configs/benchmark.json. Serves each model with the pinned upstream
llama.cpp image using identical flags (fairness: same engine, same resource
policy, same quantization IQ4_XS), runs AIPerf as the client, and writes
repeats.tsv + aggregate.tsv + manifest.json under results/current/<suite>/.

Usage:
    python3 -m bench.runner [--suite capacity] [--dry-run]
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import config, results, workload

ROOT = config.ROOT
MODEL_DIR = Path(os.environ.get("MODEL_DIR", ROOT / "models"))
IMAGE = os.environ.get("LLAMA_UPSTREAM_IMAGE", "llama-cpp-upstream:v0.4.0")
AIPERF = os.environ.get("AIPERF", "/home/jfang/venvs/aiperf/bin/aiperf")
RESULT_ROOT = ROOT / "results" / "current"

# Common serving policy (identical across the cohort; documented in the manifest).
CTX_SIZE = int(os.environ.get("CTX_SIZE", "4096"))
PARALLEL = int(os.environ.get("PARALLEL", "2"))
N_GPU_LAYERS = os.environ.get("N_GPU_LAYERS", "999")
SERVING_FLAGS = [
    "--ctx-size", str(CTX_SIZE), "--parallel", str(PARALLEL),
    "--cont-batching", "--metrics", "--n-gpu-layers", N_GPU_LAYERS,
]

# Client / gate parameters (canonical values, see configs/benchmark.json).
CONNECTION_REUSE = os.environ.get("CONNECTION_REUSE", "never")
REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "180"))
CELL_TIMEOUT = int(os.environ.get("CELL_TIMEOUT", "900"))
COOLDOWN = int(os.environ.get("COOLDOWN", "5"))
MAX_START_TEMP_C = int(os.environ.get("MAX_START_TEMP_C", "70"))
THERMAL_LIMIT_C = int(os.environ.get("THERMAL_LIMIT_C", "85"))
VRAM_LIMIT_MIB = int(os.environ.get("VRAM_LIMIT_MIB", "6000"))
STARTUP_TIMEOUT = int(os.environ.get("STARTUP_TIMEOUT", "300"))


def log(msg):
    print(f"[{time.strftime('%F %T')}] {msg}", flush=True)


def sh(*args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def gpu_temp():
    r = sh("nvidia-smi", "--query-gpu=temperature.gpu",
           "--format=csv,noheader,nounits")
    try:
        return int(r.stdout.strip().splitlines()[0].strip())
    except Exception:
        return None


def gpu_vram():
    r = sh("nvidia-smi", "--query-gpu=memory.used",
           "--format=csv,noheader,nounits")
    try:
        return int(r.stdout.strip().splitlines()[0].strip())
    except Exception:
        return None


def wait_thermal():
    start = time.time()
    while True:
        t = gpu_temp()
        if t is None or t <= MAX_START_TEMP_C:
            return
        if time.time() - start >= 120:
            log(f"WARN thermal gate timeout at {t}C")
            return
        time.sleep(3)


def docker_run_detached(container, image, port, gguf, alias):
    args = [
        "docker", "run", "-d", "--name", container,
        "--gpus", "all", "--ipc", "host",
        "-p", f"127.0.0.1:{port}:8000",
        "-v", f"{MODEL_DIR}:/models:ro",
        "--entrypoint", "/src/build/bin/llama-server",
        image,
        "--model", f"/models/{gguf}", "--alias", alias,
        "--host", "0.0.0.0", "--port", "8000",
        *SERVING_FLAGS,
    ]
    r = sh(*args)
    if r.returncode != 0:
        log(f"ERROR docker run: {r.stderr.strip()}")
        return False
    return True


def wait_ready(url, timeout=STARTUP_TIMEOUT):
    start = time.time()
    while True:
        if sh("curl", "-fsS", "--max-time", "2", f"{url}/health").returncode == 0:
            return True
        if time.time() - start >= timeout:
            return False
        time.sleep(2)


def oom_check(container):
    r = sh("docker", "logs", container)
    text = (r.stdout + r.stderr).lower()
    for pat in ("out of memory", "cuda error", "failed to allocate"):
        if pat in text:
            return True
    return False


class Telemetry:
    def __init__(self, path):
        self.path = path
        self.proc = None

    def start(self):
        f = open(self.path, "w")
        self.proc = subprocess.Popen(
            ["nvidia-smi",
             "--query-gpu=timestamp,name,temperature.gpu,utilization.gpu,"
             "utilization.memory,memory.used,power.draw,clocks.sm,clocks.mem",
             "--format=csv", "-lms", "500"],
            stdout=f, stderr=subprocess.DEVNULL)

    def stop(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None


def run_cell(arm, model_name, url, container, conc, rep, out_dir, workload_path,
             requests, warmup, osl, seed, suite="capacity", isl="raw",
             ref_tokenizer=None):
    """Run one AIPerf cell and return a results dict (row)."""
    artifact = os.path.join(out_dir, "artifacts")
    os.makedirs(artifact, exist_ok=True)
    gpu_csv = os.path.join(out_dir, "gpu.csv")
    aiperf_log = os.path.join(out_dir, "aiperf.log")

    if not docker_run_detached(container, IMAGE, _port(url), _gguf(model_name), model_name):
        return None
    if not wait_ready(url):
        log(f"ERROR {arm} did not become ready")
        sh("docker", "rm", "-f", container)
        return None

    sh("curl", "-fsS", f"{url}/props", "-o", os.path.join(out_dir, "props.json"))

    tele = Telemetry(gpu_csv)
    tele.start()
    cmd = [
        AIPERF, "profile",
        "--model", model_name,
        "--url", url,
        "--endpoint-type", "chat",
        "--streaming",
        "--connection-reuse-strategy", CONNECTION_REUSE,
        "--use-legacy-max-tokens",
        "--use-server-token-count",
        "--request-timeout-seconds", str(REQUEST_TIMEOUT),
        "--wait-for-model-timeout", "10",
        "--wait-for-model-mode", "both",
        "--concurrency", str(conc),
        "--request-count", str(requests),
        "--warmup-request-count", str(warmup),
        "--random-seed", str(seed),
        "--osl", str(osl),
        "--extra-inputs", '{"temperature":0,"ignore_eos":true,"cache_prompt":false}',
        "--artifact-dir", artifact,
        "--profile-export-level", "records",
        "--no-auto-plot",
    ]
    if isl == "raw":
        cmd += [
            "--tokenizer", "builtin",
            "--input-file", workload_path,
            "--custom-dataset-type", "single_turn",
            "--dataset-sampling-strategy", "sequential",
        ]
    else:
        # Numeric ISL: synthetic token-controlled inputs via a reference tokenizer.
        cmd += [
            "--tokenizer", ref_tokenizer or "Qwen/Qwen3-4B",
            "--apply-chat-template", "--isl", str(isl),
        ]
    t0 = time.time()
    out, err = "", ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=CELL_TIMEOUT)
        rc = r.returncode
        out, err = r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        rc = 124
        err = "CELL TIMEOUT"
    elapsed = time.time() - t0
    tele.stop()

    with open(aiperf_log, "w") as f:
        f.write(out)
        f.write("\n=== STDERR ===\n")
        f.write(err)

    oom = oom_check(container)
    logr = sh("docker", "logs", container)
    with open(os.path.join(out_dir, "server.log"), "w") as f:
        f.write(logr.stdout)
        f.write(logr.stderr)
    sh("docker", "stop", container)
    sh("docker", "rm", "-f", container)

    row = results.cell_result(arm, suite, str(isl), conc, rep, rc, artifact,
                              gpu_csv, max_error_rate=0.5)
    row["_elapsed"] = f"{elapsed:.0f}"
    row["_oom"] = "yes" if oom else "no"
    row["error_types"] = json.dumps(dict(results.extract_error_types(artifact)),
                                    sort_keys=True)
    return row


def _port(url):
    return url.rsplit(":", 1)[1]


def _gguf(model_name):
    return model_name + ".gguf"


def rotate(items, k):
    k %= len(items)
    return items[k:] + items[:k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="capacity",
                    choices=["capacity", "reliability", "shape"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    bench = config.load_benchmark()
    cohort = config.cohorts().get("mainstream_8_9b", {})
    quant = cohort.get("quantization", "IQ4_XS")

    arms = [m for m in config.models()
            if m.get("cohort") == "mainstream_8_9b" and m.get("enabled")]
    if not arms:
        log("no enabled mainstream_8_9b models")
        return 1

    seed = bench["sampling"]["seed"]

    # Cell plan: (suite, isl, osl, concs, requests, repeats, warmup).
    if args.suite == "capacity":
        plan = [("capacity", "raw", bench["output_length"]["default"],
                 bench["concurrency"]["capacity"], bench["requests"]["capacity"],
                 bench["repeats"]["capacity"], bench["warmup"]["capacity"])]
    elif args.suite == "reliability":
        plan = [("reliability", "raw", bench["output_length"]["default"],
                 bench["concurrency"]["reliability"],
                 bench["requests"]["reliability"],
                 bench["repeats"]["reliability"], bench["warmup"]["reliability"])]
    else:  # shape
        plan = []
        for name in bench["shape_profiles"]["order"]:
            p = bench["shape_profiles"]["profiles"][name]
            plan.append((f"shape_{name}", p["isl"], p["osl"],
                         bench["concurrency"]["shape"], bench["requests"]["shape"],
                         bench["repeats"]["shape"], bench["warmup"]["shape"]))

    suite_root = RESULT_ROOT / args.suite
    suite_root.mkdir(parents=True, exist_ok=True)
    workload_path = suite_root / "model_workload.jsonl"
    workload_sha = workload.write_workload_jsonl(str(workload_path))

    rows_jsonl = suite_root / "rows.jsonl"
    completed = set()
    all_rows = []
    if rows_jsonl.exists():
        for line in open(rows_jsonl, encoding="utf-8"):
            try:
                r = json.loads(line)
                all_rows.append(r)
                completed.add((r["suite"], r["arm"], r["isl"],
                               r["concurrency"], r["repeat"]))
            except Exception:
                continue

    for suite, isl, osl, concs, requests, repeats, warmup in plan:
        for rep in range(repeats):
            for m in rotate(arms, rep):
                arm = m["arm"]
                url = f"http://127.0.0.1:{m['port']}"
                container = "bench-" + arm.replace("_", "-")
                model_name = m["gguf_filename"].removesuffix(".gguf")
                for conc in concs:
                    key = (suite, arm, str(isl), str(conc), str(rep + 1))
                    if key in completed:
                        log(f"skip (done) suite={suite} arm={arm} c={conc} "
                            f"rep={rep + 1}/{repeats}")
                        continue
                    log(f"cell suite={suite} arm={arm} isl={isl} c={conc} "
                        f"rep={rep + 1}/{repeats}")
                    if args.dry_run:
                        continue
                    wait_thermal()
                    out_dir = (suite_root / arm / f"isl_{isl}" /
                               f"c_{conc}" / f"rep_{rep + 1}")
                    out_dir.mkdir(parents=True, exist_ok=True)
                    row = run_cell(arm, model_name, url, container, conc,
                                   rep + 1, str(out_dir), str(workload_path),
                                   requests, warmup, osl, seed,
                                   suite=suite, isl=isl)
                    if row is None:
                        log(f"FAIL startup {arm} c={conc}")
                        continue
                    all_rows.append(row)
                    with open(rows_jsonl, "a", encoding="utf-8") as f:
                        f.write(json.dumps(row) + "\n")
                    log(f"  -> status={row['status']} "
                        f"ok={row['successful_requests']}/"
                        f"{row['attempted_requests']} vram={row['peak_vram_mib']}MiB "
                        f"oom={row['_oom']} ttft_p50={row['ttft_p50_ms']}ms")
                    time.sleep(COOLDOWN)

    if args.dry_run:
        log("dry run: nothing executed")
        return 0

    results.write_repeats_tsv(all_rows, str(suite_root / "repeats.tsv"))
    results.write_aggregate_tsv(results.aggregate(all_rows),
                                str(suite_root / "aggregate.tsv"))
    if args.suite == "reliability":
        results.write_reliability_tsv(results.reliability_summary(all_rows),
                                      str(suite_root / "reliability.tsv"))
    _write_manifest(suite_root, bench, arms, quant, workload_sha,
                    args.suite, seed)
    log(f"wrote repeats.tsv + aggregate.tsv ({len(all_rows)} rows)")
    return 0


def _write_manifest(suite_dir, bench, arms, quant, workload_sha, suite, seed):
    import datetime
    commit = sh("git", "-C", str(ROOT), "rev-parse", "HEAD").stdout.strip()
    gpu = sh("nvidia-smi", "--query-gpu=name,driver_version,memory.total",
             "--format=csv,noheader,nounits").stdout.strip().splitlines()[0]
    models = {}
    for m in arms:
        gguf = m["gguf_filename"]
        sha = m.get("sha256")
        models[gguf] = {
            "display_name": m["display_name"],
            "actual_parameter_count": m.get("actual_parameter_count"),
            "sha256": sha,
            "quantization": m["quantization"],
            "gguf_source": m.get("gguf_source"),
            "upstream_repo": m["upstream_repo"],
            "license": m.get("license"),
        }
    manifest = {
        "suite": suite,
        "git_commit": commit,
        "aiperf_version": "0.12.0",
        "engine": "ggml-org/llama.cpp v0.4.0 (pinned)",
        "image": IMAGE,
        "gpu": gpu,
        "serving_flags": SERVING_FLAGS,
        "quantization": quant,
        "workload_sha256": workload_sha,
        "config": {
            "concurrency": bench["concurrency"].get(suite),
            "repeats": bench["repeats"].get(suite),
            "requests_per_cell": bench["requests"].get(suite),
            "output_tokens": bench["output_length"]["default"],
            "seed": seed,
            "temperature": 0, "ignore_eos": True, "cache_prompt": False,
            "connection_reuse": CONNECTION_REUSE,
            "ctx_size": CTX_SIZE, "parallel": PARALLEL,
            "n_gpu_layers": N_GPU_LAYERS,
        },
        "models": models,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    with open(suite_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
