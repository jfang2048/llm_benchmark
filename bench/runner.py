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
# AIPerf is expected on PATH; override with AIPERF=/path/to/aiperf if not.
AIPERF = os.environ.get("AIPERF", "aiperf")
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
# Concurrency used for the rate-based (open-loop/soak) suites: high enough that
# the server is not artificially serialized, matching the capacity sweep max.
RATE_CONC = int(os.environ.get("RATE_CONC", "8"))


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


def _arm_info(m):
    return (m["arm"], f"http://127.0.0.1:{m['port']}",
            "bench-" + m["arm"].replace("_", "-"),
            m["gguf_filename"].removesuffix(".gguf"))


def rotate(items, k):
    k %= len(items)
    return items[k:] + items[:k]


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _base_rates():
    """Return {arm: max request_tps} from the committed capacity aggregate."""
    import csv
    p = RESULT_ROOT / "capacity" / "aggregate.tsv"
    rates = {}
    if not p.exists():
        return rates
    for r in csv.DictReader(open(p, encoding="utf-8"), delimiter="\t"):
        tps = _num(r.get("request_tps_mean"))
        if tps:
            rates[r["arm"]] = max(rates.get(r["arm"], 0.0), tps)
    return rates


def _aiperf_base(artifact):
    return [AIPERF, "profile", "--endpoint-type", "chat", "--streaming",
            "--connection-reuse-strategy", CONNECTION_REUSE,
            "--use-legacy-max-tokens", "--use-server-token-count",
            "--request-timeout-seconds", str(REQUEST_TIMEOUT),
            "--wait-for-model-timeout", "10", "--wait-for-model-mode", "both",
            "--artifact-dir", artifact, "--profile-export-level", "records",
            "--no-auto-plot"]


def _finish_cell(cmd, arm, suite, isl, conc, rep, out_dir, artifact, gpu_csv,
                 container, timeout):
    tele = Telemetry(gpu_csv)
    tele.start()
    out, err = "", ""
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        rc = r.returncode
        out, err = r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        rc = 124
        err = "CELL TIMEOUT"
    elapsed = time.time() - t0
    tele.stop()
    with open(os.path.join(out_dir, "aiperf.log"), "w") as f:
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


def _serve(arm, model_name, url, container, out_dir):
    artifact = os.path.join(out_dir, "artifacts")
    os.makedirs(artifact, exist_ok=True)
    gpu_csv = os.path.join(out_dir, "gpu.csv")
    if not docker_run_detached(container, IMAGE, _port(url), _gguf(model_name),
                               model_name):
        return None
    if not wait_ready(url):
        log(f"ERROR {arm} did not become ready")
        sh("docker", "rm", "-f", container)
        return None
    sh("curl", "-fsS", f"{url}/props", "-o", os.path.join(out_dir, "props.json"))
    return artifact, gpu_csv


def run_rate_cell(arm, model_name, url, container, conc, rep, out_dir,
                  workload_path, rate, duration, osl, seed, suite, isl):
    served = _serve(arm, model_name, url, container, out_dir)
    if served is None:
        return None
    artifact, gpu_csv = served
    cmd = (_aiperf_base(artifact)
           + ["--model", model_name, "--url", url,
              "--request-rate", f"{rate:.4f}", "--arrival-pattern", "poisson",
              "--concurrency", str(conc),
              "--benchmark-duration", str(duration), "--slice-duration", "5",
              "--warmup-request-count", "5", "--random-seed", str(seed),
              "--osl", str(osl),
              "--extra-inputs", '{"temperature":0,"ignore_eos":true,"cache_prompt":false}',
              "--tokenizer", "builtin", "--input-file", workload_path,
              "--custom-dataset-type", "single_turn",
              "--dataset-sampling-strategy", "sequential"])
    return _finish_cell(cmd, arm, suite, isl, conc, rep, out_dir, artifact,
                        gpu_csv, container, int(duration) + 120)


def run_sessions_cell(arm, model_name, url, container, rep, out_dir, osl,
                      seed, cache, isl="raw"):
    served = _serve(arm, model_name, url, container, out_dir)
    if served is None:
        return None
    artifact, gpu_csv = served
    cache_v = "true" if cache else "false"
    cmd = (_aiperf_base(artifact)
           + ["--model", model_name, "--url", url,
              "--concurrency", "1", "--request-count", "80",
              "--warmup-request-count", "5", "--random-seed", str(seed),
              "--osl", str(osl),
              "--extra-inputs",
              '{"temperature":0,"ignore_eos":true,"cache_prompt":' + cache_v + '}',
              "--conversation-num", "20", "--conversation-turn-mean", "4",
              "--conversation-turn-delay-mean", "0", "--tokenizer", "builtin"])
    return _finish_cell(cmd, arm, "sessions", isl, 1, rep, out_dir, artifact,
                        gpu_csv, container, CELL_TIMEOUT)


def run_startup_cell(arm, model_name, url, container, rep, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    if not docker_run_detached(container, IMAGE, _port(url), _gguf(model_name),
                               model_name):
        return None
    ready_at = None
    while time.time() - t0 < STARTUP_TIMEOUT:
        if sh("curl", "-fsS", "--max-time", "2", f"{url}/health").returncode == 0:
            ready_at = time.time()
            break
        time.sleep(0.5)
    if ready_at is None:
        sh("docker", "rm", "-f", container)
        return None
    ttft_s = None
    try:
        out = subprocess.run(
            ["curl", "-sN", "--max-time", "120", "-w", "%{time_starttransfer}",
             "-o", os.devnull, "-H", "Content-Type: application/json",
             "-d", json.dumps({"model": model_name,
                               "messages": [{"role": "user", "content": "Say hello."}],
                               "max_tokens": 16, "temperature": 0}),
             f"{url}/v1/chat/completions"],
            capture_output=True, text=True, timeout=130)
        v = out.stdout.strip()
        ttft_s = float(v) if v else None
    except Exception:
        ttft_s = None
    sh("docker", "stop", container)
    sh("docker", "rm", "-f", container)
    ok = ttft_s is not None
    row = {
        "arm": arm, "suite": "startup", "isl": "raw", "concurrency": "1",
        "repeat": str(rep), "status": "PASS" if ok else "FAIL",
        "error_rate_pct": "", "attempted_requests": "1",
        "successful_requests": "1" if ok else "0",
        "failed_requests": "0" if ok else "1",
        "success_rate_pct": "100.0000" if ok else "0.0000",
        "input_tokens_avg": "", "output_tokens_avg": "",
        "ttft_avg_ms": f"{ttft_s * 1000:.2f}" if ok else "",
        "ttft_p50_ms": f"{ttft_s * 1000:.2f}" if ok else "",
        "ttft_p95_ms": "", "ttft_p99_ms": "",
        "itl_avg_ms": "", "itl_p50_ms": "", "itl_p95_ms": "", "itl_p99_ms": "",
        "latency_avg_ms": "", "latency_p50_ms": "", "latency_p95_ms": "",
        "latency_p99_ms": "", "request_tps": "", "output_tps": "",
        "peak_vram_mib": "", "peak_power_w": "", "avg_gpu_util_pct": "",
        "peak_temp_c": "", "gpu_energy_j": "", "gpu_j_per_request": "",
        "gpu_j_per_output_token": "", "_elapsed": f"{time.time() - t0:.0f}",
        "_oom": "no",
        "ready_ms": f"{(ready_at - t0) * 1000:.1f}",
        "first_token_ms": f"{ttft_s * 1000:.1f}" if ok else "",
        "cold_start_ms": f"{(ready_at + ttft_s - t0) * 1000:.1f}" if ok else "",
    }
    return row


def _write_startup_summary(rows, path):
    import csv as _csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f, delimiter="\t")
        w.writerow(["arm", "repeat", "ready_ms", "first_token_ms",
                    "cold_start_ms"])
        for r in rows:
            w.writerow([r["arm"], r["repeat"], r.get("ready_ms", ""),
                        r.get("first_token_ms", ""), r.get("cold_start_ms", "")])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="capacity",
                    choices=["capacity", "reliability", "shape", "startup",
                             "soak", "open-loop", "sessions"])
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
    osl_default = bench["output_length"]["default"]

    suite_root = RESULT_ROOT / args.suite
    suite_root.mkdir(parents=True, exist_ok=True)
    workload_path = str(suite_root / "model_workload.jsonl")
    workload_sha = workload.write_workload_jsonl(workload_path)

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

    def append(row):
        if row is None:
            return
        all_rows.append(row)
        with open(rows_jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    # --- rate/timing/multi-turn suites ---
    if args.suite in ("startup", "soak", "open-loop", "sessions"):
        rates = _base_rates()
        if args.suite == "startup":
            reps = bench["repeats"]["startup"]
            for m in arms:
                arm, url, container, model_name = _arm_info(m)
                for rep in range(reps):
                    key = ("startup", arm, "raw", "1", str(rep + 1))
                    if key in completed:
                        continue
                    log(f"cell suite=startup arm={arm} rep={rep + 1}/{reps}")
                    if args.dry_run:
                        continue
                    out_dir = suite_root / arm / f"rep_{rep + 1}"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    row = run_startup_cell(arm, model_name, url, container,
                                           rep + 1, str(out_dir))
                    if row is None:
                        log(f"FAIL startup {arm}")
                        continue
                    append(row)
                    log(f"  -> {row['status']} cold_start={row['cold_start_ms']}ms")
                    time.sleep(COOLDOWN)
        elif args.suite == "soak":
            duration = bench["soak"]["duration_seconds"]
            frac = bench["soak"]["load_fraction"]
            for m in arms:
                arm, url, container, model_name = _arm_info(m)
                rate = rates.get(arm, 0.5) * frac
                key = ("soak", arm, "raw", "1", "1")
                if key in completed:
                    continue
                log(f"cell suite=soak arm={arm} rate={rate:.3f} dur={duration}s")
                if args.dry_run:
                    continue
                out_dir = suite_root / arm / "rep_1"
                out_dir.mkdir(parents=True, exist_ok=True)
                row = run_rate_cell(arm, model_name, url, container, RATE_CONC, 1,
                                    str(out_dir), workload_path, rate, duration,
                                    osl_default, seed, "soak", "raw")
                if row is None:
                    log(f"FAIL serve {arm}")
                    continue
                append(row)
                log(f"  -> {row['status']} temp={row['peak_temp_c']}C "
                    f"power={row['peak_power_w']}W")
                time.sleep(COOLDOWN)
        elif args.suite == "open-loop":
            fracs = bench["open_loop"]["load_fractions"]
            duration = 120
            for m in arms:
                arm, url, container, model_name = _arm_info(m)
                R = rates.get(arm, 0.5)
                for frac in fracs:
                    isl = f"{frac:.2f}"
                    key = ("openloop", arm, isl, "1", "1")
                    if key in completed:
                        continue
                    rate = R * frac
                    log(f"cell suite=openloop arm={arm} frac={frac} "
                        f"rate={rate:.3f}")
                    if args.dry_run:
                        continue
                    out_dir = suite_root / arm / f"frac_{frac:.2f}"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    row = run_rate_cell(arm, model_name, url, container, RATE_CONC, 1,
                                        str(out_dir), workload_path, rate,
                                        duration, osl_default, seed,
                                        "openloop", isl)
                    if row is None:
                        log(f"FAIL serve {arm}")
                        continue
                    append(row)
                    log(f"  -> {row['status']} err={row['error_rate_pct']}% "
                        f"tps={row['request_tps']}")
                    time.sleep(COOLDOWN)
        else:  # sessions
            for m in arms:
                arm, url, container, model_name = _arm_info(m)
                for cache in (False, True):
                    isl = "cache" if cache else "nocache"
                    key = ("sessions", arm, isl, "1", "1")
                    if key in completed:
                        continue
                    log(f"cell suite=sessions arm={arm} cache_prompt={cache}")
                    if args.dry_run:
                        continue
                    out_dir = suite_root / arm / isl
                    out_dir.mkdir(parents=True, exist_ok=True)
                    row = run_sessions_cell(arm, model_name, url, container, 1,
                                            str(out_dir), osl_default, seed,
                                            cache, isl=isl)
                    if row is None:
                        log(f"FAIL serve {arm}")
                        continue
                    append(row)
                    log(f"  -> {row['status']} ttft_p50={row['ttft_p50_ms']}ms")
                    time.sleep(COOLDOWN)

        if args.dry_run:
            log("dry run: nothing executed")
            return 0
        results.write_repeats_tsv(all_rows, str(suite_root / "repeats.tsv"))
        results.write_aggregate_tsv(results.aggregate(all_rows),
                                    str(suite_root / "aggregate.tsv"))
        if args.suite == "startup":
            _write_startup_summary(all_rows, str(suite_root / "startup.tsv"))
        _write_manifest(suite_root, bench, arms, quant, workload_sha,
                        args.suite, seed)
        log(f"wrote repeats.tsv + aggregate.tsv ({len(all_rows)} rows)")
        return 0

    # --- capacity / reliability / shape (plan-based) ---
    if args.suite == "capacity":
        plan = [("capacity", "raw", osl_default,
                 bench["concurrency"]["capacity"], bench["requests"]["capacity"],
                 bench["repeats"]["capacity"], bench["warmup"]["capacity"])]
    elif args.suite == "reliability":
        plan = [("reliability", "raw", osl_default,
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

    for suite, isl, osl, concs, requests, repeats, warmup in plan:
        for rep in range(repeats):
            for m in rotate(arms, rep):
                arm, url, container, model_name = _arm_info(m)
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
                                   rep + 1, str(out_dir), workload_path,
                                   requests, warmup, osl, seed,
                                   suite=suite, isl=isl,
                                   ref_tokenizer=m["upstream_repo"])
                    if row is None:
                        log(f"FAIL startup {arm} c={conc}")
                        continue
                    append(row)
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
