#!/usr/bin/env bash
# Controlled MODEL benchmark: Spark-X2.5-4B vs Qwen3-4B on llama.cpp.
#
# This is the canonical benchmark runner. It reproduces the validated final
# experiment (historical run 20260904_192416) without changing the methodology:
#
#   engine       llama.cpp (same binary + same serving flags for both arms)
#   quantization Q4_K_M (both)
#   workload     identical raw-text prompts, identical order, temperature=0,
#                ignore_eos=true, cache_prompt=false
#   matrix       2 models x {1,2,3,4} concurrency x 4 repeats = 32 cells
#   per cell     80 profiling requests (final) or 8 (smoke), 5 warmup (1 smoke)
#   output cap   128 tokens (final) or 32 (smoke)
#
# Usage:
#   MODE=smoke  ./scripts/benchmark.sh     # fast pipeline validation
#   MODE=final  ./scripts/benchmark.sh     # full validated matrix (default)
#   ./scripts/benchmark.sh --help
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${MODEL_DIR:-$ROOT/models}"
[[ -f "$ROOT/benchmark/config.env" ]] && set -a && . "$ROOT/benchmark/config.env" && set +a || true
MODE="${MODE:-final}"
# v1 (final/smoke) keeps the historical results/runs/ layout; Benchmark v2
# suites write to results/v2/runs/.
case "$MODE" in
  final|smoke) RESULT_ROOT="$ROOT/results/runs" ;;
  *)           RESULT_ROOT="$ROOT/results/v2/runs" ;;
esac

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'EOF'
Controlled MODEL benchmark (Spark-X2.5-4B vs Qwen3-4B, llama.cpp)

Usage:
  ./scripts/benchmark.sh --help
  MODE=smoke        ./scripts/benchmark.sh   fast pipeline validation
  MODE=final        ./scripts/benchmark.sh   full validated matrix (80 req, 5 warmup, 4 repeats, 128 tok)
  MODE=reliability  ./scripts/benchmark.sh   P0 transport-reliability gate (2 models x {1,4} x 200 req)

Environment overrides (all optional):
  MODE, REQUESTS, WARMUP, REPEATS, CONCURRENCIES, OUTPUT_TOKENS, SEED,
  MAX_ERROR_RATE, STARTUP_TIMEOUT, COOLDOWN_SECONDS, REQUEST_TIMEOUT,
  CELL_TIMEOUT, MODEL_DIR, CONNECTION_REUSE, RELIABILITY_MIN_SUCCESS, FORCE_UNSTABLE

Transport note: CONNECTION_REUSE defaults to 'never' (fresh connection per
request) to avoid aiohttp pooled-connection reuse racing with the llama.cpp
HTTP server closing keep-alive connections (root cause of ServerDisconnectedError).
EOF
  exit 0
fi

RUN_ID="$(date +%Y%m%d_%H%M%S)"
OUT="$RESULT_ROOT/$RUN_ID"
SUMMARY="$OUT/summary.txt"
REPORT="$OUT/model_comparison.md"
case "$MODE" in
  final|smoke) ROWS="$OUT/results.tsv" ;;
  *)           ROWS="$OUT/repeats.tsv" ;;
esac
WORKLOAD="$OUT/model_workload.jsonl"
ERRORS="$OUT/error_details.tsv"
CONFIG_REPORT="$OUT/runtime_config.txt"

# Recognized modes. final/smoke preserve the historical methodology; reliability
# is the Benchmark v2 P0 gate. Other v2 suites are staged (see BACKLOG.md).
case "$MODE" in
  final)
    REQUESTS="${REQUESTS:-80}"
    WARMUP="${WARMUP:-5}"
    REPEATS="${REPEATS:-4}"
    read -r -a CONCURRENCIES <<< "${CONCURRENCIES:-1 2 3 4}"
    OUTPUT_TOKENS="${OUTPUT_TOKENS:-128}"
    ;;
  reliability)
    # P0 transport-reliability gate: 2 models x {c1, c4} x >=200 requests.
    REQUESTS="${REQUESTS:-200}"
    WARMUP="${WARMUP:-10}"
    REPEATS="${REPEATS:-1}"
    read -r -a CONCURRENCIES <<< "${CONCURRENCIES:-1 4}"
    OUTPUT_TOKENS="${OUTPUT_TOKENS:-128}"
    ;;
  capacity)
    # P2 closed-loop capacity discovery: adaptive sweep, stop on reliability /
    # OOM / thermal. Default sweep 1 2 3 4 6 8 (server has --parallel 4).
    REQUESTS="${REQUESTS:-60}"
    WARMUP="${WARMUP:-5}"
    REPEATS="${REPEATS:-1}"
    read -r -a CONCURRENCIES <<< "${CONCURRENCIES:-1 2 3 4 6 8}"
    OUTPUT_TOKENS="${OUTPUT_TOKENS:-128}"
    ;;
  shape)
    # P3 token-shape benchmark: ISL/OSL profiles at c1 and c4.
    REQUESTS="${REQUESTS:-60}"
    WARMUP="${WARMUP:-5}"
    REPEATS="${REPEATS:-1}"
    read -r -a CONCURRENCIES <<< "${CONCURRENCIES:-1 4}"
    OUTPUT_TOKENS="${OUTPUT_TOKENS:-128}"
    ;;
  open-loop)
    # P4 open-loop load at fractions of stable capacity (Poisson arrival).
    REQUESTS="${REQUESTS:-1}"   # sanity gate only; cells use OPEN_LOOP_REQUESTS
    WARMUP="${WARMUP:-10}"
    OUTPUT_TOKENS="${OUTPUT_TOKENS:-128}"
    ;;
  startup)
    # P5 process cold-start measurement (container start -> API ready -> first token).
    REQUESTS="${REQUESTS:-1}"
    WARMUP="${WARMUP:-0}"
    OUTPUT_TOKENS="${OUTPUT_TOKENS:-16}"
    ;;
  soak)
    # P5 sustained-load soak at ~75% of stable capacity for a fixed duration.
    REQUESTS="${REQUESTS:-1}"
    WARMUP="${WARMUP:-10}"
    OUTPUT_TOKENS="${OUTPUT_TOKENS:-128}"
    ;;
  sessions)
    # P7 multi-turn sessions (latency by turn) + optional prefix-cache experiment.
    REQUESTS="${REQUESTS:-80}"
    WARMUP="${WARMUP:-5}"
    OUTPUT_TOKENS="${OUTPUT_TOKENS:-64}"
    ;;
  backend)
    # P8 engine comparison: same Qwen3-4B GGUF on llama.cpp vs vLLM+GGUF.
    REQUESTS="${REQUESTS:-80}"
    WARMUP="${WARMUP:-5}"
    REPEATS="${REPEATS:-4}"
    read -r -a CONCURRENCIES <<< "${CONCURRENCIES:-1 2 4}"
    OUTPUT_TOKENS="${OUTPUT_TOKENS:-128}"
    ;;
  smoke|*)
    REQUESTS="${REQUESTS:-8}"
    WARMUP="${WARMUP:-1}"
    REPEATS="${REPEATS:-1}"
    read -r -a CONCURRENCIES <<< "${CONCURRENCIES:-1}"
    OUTPUT_TOKENS="${OUTPUT_TOKENS:-32}"
    ;;
esac

SEED="${SEED:-42}"
REPEATS="${REPEATS:-1}"
MAX_ERROR_RATE="${MAX_ERROR_RATE:-1.0}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-180}"
COOLDOWN_SECONDS="${COOLDOWN_SECONDS:-5}"
CELL_TIMEOUT="${CELL_TIMEOUT:-1800}"
MAX_START_TEMP_C="${MAX_START_TEMP_C:-70}"
TEMP_WAIT_TIMEOUT="${TEMP_WAIT_TIMEOUT:-120}"

# Transport reliability controls.
# 'never' avoids aiohttp pooled-connection reuse racing with the llama.cpp HTTP
# server closing keep-alive connections (root cause of ServerDisconnectedError).
CONNECTION_REUSE="${CONNECTION_REUSE:-never}"
# Minimum transport success rate (%) for a publication-grade final run.
RELIABILITY_MIN_SUCCESS="${RELIABILITY_MIN_SUCCESS:-99.5}"
# When set, an unreliable final run proceeds but is marked INVALID_FOR_RANKING.
FORCE_UNSTABLE="${FORCE_UNSTABLE:-0}"

# Isolated ports (everyday deployments use 8000/8001).
declare -A URL=(
  [spark_llama]="http://127.0.0.1:8100"
  [qwen_llama]="http://127.0.0.1:8101"
  [qwen_vllm_gguf]="http://127.0.0.1:8102"
  [qwen_vllm_awq]="http://127.0.0.1:8103"
)
declare -A CONTAINER=(
  [spark_llama]="bench-spark-llama"
  [qwen_llama]="bench-qwen-llama"
  [qwen_vllm_gguf]="bench-qwen-vllm-gguf"
  [qwen_vllm_awq]="bench-qwen-vllm-awq"
)
declare -A MODEL=(
  [spark_llama]="Spark-X2.5-4B-Q4_K_M"
  [qwen_llama]="Qwen3-4B-Q4_K_M"
  [qwen_vllm_gguf]="Qwen3-4B-Q4_K_M"
  [qwen_vllm_awq]="Qwen3-4B-AWQ"
)
# Backend comparison uses the same Qwen GGUF on two engines; every other suite
# compares the two models on llama.cpp.
if [[ "$MODE" == "backend" ]]; then
  ALL_ARMS=(qwen_llama qwen_vllm_gguf)
else
  ALL_ARMS=(spark_llama qwen_llama)
fi

mkdir -p "$OUT"
need(){ command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing $1" >&2; exit 1; }; }
for x in docker curl python3 aiperf nvidia-smi flock timeout; do need "$x"; done

LOCK_FILE="$ROOT/benchmark/.cross_benchmark.lock"
PID_FILE="$ROOT/benchmark/.cross_benchmark.pid"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "ERROR: another benchmark holds $LOCK_FILE" >&2
  [[ -f "$PID_FILE" ]] && echo "Owner PID: $(cat "$PID_FILE" 2>/dev/null)" >&2
  exit 9
fi
printf '%s\n' "$$" > "$PID_FILE"

EVENT_PID=""
TELE_PID=""
CURRENT_EVENT_FILE=""
CURRENT_START_EPOCH=""

log(){ printf '[%s] %s\n' "$(date '+%F %T')" "$*" | tee -a "$SUMMARY"; }
is_running(){ [[ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || true)" == true ]]; }

stop_all_models(){
  local c
  for c in spark-x25 vllm bench-spark-llama bench-qwen-llama bench-qwen-vllm-gguf bench-qwen-vllm-awq; do
    docker inspect "$c" >/dev/null 2>&1 || continue
    is_running "$c" && docker stop "$c" >/dev/null 2>&1 || true
  done
}

declare -A ORIG=()
for c in spark-x25 vllm; do
  docker inspect "$c" >/dev/null 2>&1 || continue
  is_running "$c" && ORIG[$c]=1 || ORIG[$c]=0
done
restore(){
  local c
  [[ -n "${EVENT_PID:-}" ]] && kill "$EVENT_PID" >/dev/null 2>&1 || true
  [[ -n "${TELE_PID:-}" ]] && kill "$TELE_PID" >/dev/null 2>&1 || true
  stop_all_models
  for c in spark-x25 vllm; do
    [[ "${ORIG[$c]:-0}" == 1 ]] && docker start "$c" >/dev/null 2>&1 || true
  done
  rm -f "$PID_FILE"
}
trap restore EXIT INT TERM

start_event_capture(){
  local c="$1" file="$2"
  mkdir -p "$(dirname "$file")"
  CURRENT_START_EPOCH="$(date +%s)"
  CURRENT_EVENT_FILE="$file"
  docker events --since "$CURRENT_START_EPOCH" \
    --filter type=container --filter "container=$c" \
    --format '{{json .}}' > "$file" 2>&1 &
  EVENT_PID=$!
}
stop_event_capture(){
  [[ -n "${EVENT_PID:-}" ]] && kill "$EVENT_PID" >/dev/null 2>&1 || true
  [[ -n "${EVENT_PID:-}" ]] && wait "$EVENT_PID" 2>/dev/null || true
  EVENT_PID=""
}

wait_thermal(){
  local start now t
  start=$(date +%s)
  while :; do
    t=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>/dev/null | head -n1 | tr -d ' ')
    [[ "$t" =~ ^[0-9]+$ ]] || return 0
    (( t <= MAX_START_TEMP_C )) && return 0
    now=$(date +%s)
    (( now-start >= TEMP_WAIT_TIMEOUT )) && { log "WARN: thermal gate timed out at ${t}C"; return 0; }
    sleep 3
  done
}

wait_api(){
  local c="$1" u="$2" start now
  start=$(date +%s)
  while :; do
    is_running "$c" || return 1
    if curl -fsS --max-time 2 "$u/health" >/dev/null 2>&1 \
       && curl -fsS --max-time 2 "$u/v1/models" >/dev/null 2>&1; then
      return 0
    fi
    now=$(date +%s)
    (( now-start >= STARTUP_TIMEOUT )) && return 1
    sleep 2
  done
}

save_startup_failure(){
  local arm="$1"
  local c="${CONTAINER[$arm]}"
  local dir="$OUT/startup-failures/$arm"
  mkdir -p "$dir"
  docker inspect "$c" > "$dir/inspect.json" 2>&1 || true
  docker inspect "$c" --format 'Status={{.State.Status}} Running={{.State.Running}} ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}} Error={{.State.Error}} StartedAt={{.State.StartedAt}} FinishedAt={{.State.FinishedAt}} RestartCount={{.RestartCount}}' \
    > "$dir/state.txt" 2>&1 || true
  if [[ -n "${CURRENT_START_EPOCH:-}" ]]; then
    docker logs --timestamps --since "$CURRENT_START_EPOCH" "$c" > "$dir/docker-current-run.log" 2>&1 || true
  else
    docker logs --timestamps --tail 400 "$c" > "$dir/docker-current-run.log" 2>&1 || true
  fi
  [[ -n "${CURRENT_EVENT_FILE:-}" && -f "$CURRENT_EVENT_FILE" ]] && cp "$CURRENT_EVENT_FILE" "$dir/docker-events.jsonl" 2>/dev/null || true
  log "STARTUP FAILURE $arm: $(cat "$dir/state.txt" 2>/dev/null)"
}

start_arm(){
  local arm="$1"
  local c="${CONTAINER[$arm]}"
  local ev="$2"
  stop_all_models
  log "START arm=$arm container=$c url=${URL[$arm]}"
  wait_thermal
  stop_event_capture
  start_event_capture "$c" "$ev"
  docker start "$c" >/dev/null || { stop_event_capture; save_startup_failure "$arm"; return 1; }
  if ! wait_api "$c" "${URL[$arm]}"; then
    stop_event_capture
    save_startup_failure "$arm"
    return 1
  fi
}

preflight_config(){
  local arm c
  log "===== configuration preflight ====="
  for arm in "${ALL_ARMS[@]}"; do
    c="${CONTAINER[$arm]}"
    docker inspect "$c" >/dev/null 2>&1 || { log "FATAL: missing $c; run scripts/deploy.sh"; return 1; }
    log "OK config $arm -> $c ${URL[$arm]}"
  done
}

verify_runtime_controls(){
  log "===== runtime-control equivalence ====="
  python3 - "$CONFIG_REPORT" "${CONTAINER[spark_llama]}" "${CONTAINER[qwen_llama]}" <<'PY'
import json, subprocess, sys
out, a, b = sys.argv[1:]
objs = {}
for name in (a, b):
    j = json.loads(subprocess.check_output(["docker", "inspect", name], text=True))[0]
    objs[name] = j
def cmd(name):
    return [str(x) for x in (objs[name]["Config"].get("Cmd") or [])]
def image_id(name):
    return objs[name].get("Image", "")
aliases = {
    "ctx_size": ["--ctx-size", "-c"],
    "parallel": ["--parallel", "-np"],
    "gpu_layers": ["--n-gpu-layers", "--gpu-layers", "-ngl"],
    "batch_size": ["--batch-size", "-b"],
    "ubatch_size": ["--ubatch-size", "-ub"],
    "threads": ["--threads", "-t"],
    "threads_batch": ["--threads-batch", "-tb"],
    "cache_k": ["--cache-type-k", "-ctk"],
    "cache_v": ["--cache-type-v", "-ctv"],
    "cache_ram": ["--cache-ram"],
}
bool_aliases = {
    "flash_attn": ["--flash-attn", "-fa"],
    "kv_unified": ["--kv-unified", "-kvu"],
}
def extract(c, names):
    for i, x in enumerate(c):
        if x in names:
            if i+1 < len(c) and not c[i+1].startswith("-"):
                return c[i+1]
            return "present"
        for n in names:
            if x.startswith(n + "="):
                return x.split("=", 1)[1]
    return None
rows = []
mismatch = []
ca, cb = cmd(a), cmd(b)
if image_id(a) != image_id(b):
    mismatch.append(f"image_id differs: {image_id(a)} != {image_id(b)}")
for key, names in aliases.items():
    va, vb = extract(ca, names), extract(cb, names)
    rows.append((key, va, vb))
    if va != vb:
        mismatch.append(f"{key}: {va} != {vb}")
for key, names in bool_aliases.items():
    va, vb = extract(ca, names), extract(cb, names)
    rows.append((key, va, vb))
    if va != vb:
        mismatch.append(f"{key}: {va} != {vb}")
with open(out, "w", encoding="utf-8") as f:
    f.write(f"container_A={a}\ncontainer_B={b}\n")
    f.write(f"image_A={image_id(a)}\nimage_B={image_id(b)}\n\n")
    f.write("control\tspark\tqwen\n")
    for r in rows:
        f.write("\t".join("" if x is None else str(x) for x in r) + "\n")
    f.write("\nCMD spark:\n" + " ".join(ca) + "\n")
    f.write("\nCMD qwen:\n" + " ".join(cb) + "\n")
if mismatch:
    print("FATAL: runtime controls are not equivalent:", file=sys.stderr)
    for x in mismatch:
        print("  " + x, file=sys.stderr)
    sys.exit(1)
print("PASS: same image and same serving-control flags")
PY
  local rc=$?
  if (( rc != 0 )); then
    cat "$CONFIG_REPORT" >&2 || true
    return "$rc"
  fi
  cat "$CONFIG_REPORT" >> "$SUMMARY"
}

# Same raw bytes/order for model-effect comparison. 20 base cases -> 100 unique prompts.
cat > "$WORKLOAD" <<'JSONL'
{"text":"Explain TCP TIME_WAIT, why it exists, and when many TIME_WAIT sockets become operationally harmful. Give a concise SRE-oriented answer."}
{"text":"A Linux host has load average 18 on 8 CPUs but CPU utilization is 25 percent. Give the diagnostic sequence and exact commands."}
{"text":"A Docker container exits with code 137. Explain how to distinguish cgroup OOM, host OOM, and an external SIGKILL."}
{"text":"A Kubernetes pod is in CrashLoopBackOff. Give a minimal investigation sequence and explain what each command proves."}
{"text":"df -h shows free space but writes fail with No space left on device. List likely causes and exact validation commands."}
{"text":"Explain TTFT, inter-token latency, end-to-end latency, request throughput, token throughput, and goodput for LLM serving."}
{"text":"Why do p95 and p99 matter for an inference SLO even when average latency looks healthy?"}
{"text":"Explain prefill versus decode in transformer inference and the usual compute or memory bottleneck of each phase."}
{"text":"Explain continuous batching and why it changes throughput and tail latency under concurrent LLM requests."}
{"text":"An HTTP streaming response intermittently ends with connection reset by peer. Give a prioritized debugging checklist."}
{"text":"Explain model weight memory, KV cache, activations, CUDA graph memory, and allocator overhead in LLM inference."}
{"text":"A GPU process uses nearly all VRAM but GPU utilization oscillates between 20 and 90 percent. Explain possible causes and measurements."}
{"text":"Explain how to detect thermal throttling on an NVIDIA laptop GPU while benchmarking inference."}
{"text":"Explain why identical parameter counts do not guarantee identical inference cost across transformer models."}
{"text":"Compare latency-oriented and throughput-oriented scheduling objectives for an LLM serving system."}
{"text":"Explain why tokenizer differences make cross-model tokens-per-second comparisons imperfect."}
{"text":"Describe how to determine whether an inference service is CPU-bound, GPU-compute-bound, memory-bandwidth-bound, or queue-bound."}
{"text":"Explain Server-Sent Events framing and failure modes that cause incomplete streamed HTTP payloads."}
{"text":"Describe a reproducible benchmark methodology for comparing two local LLM inference servers."}
{"text":"Explain why a benchmark must distinguish cold-start latency, steady-state latency, saturation throughput, and failure rate."}
JSONL
python3 - "$WORKLOAD" <<'PY'
import json, os, sys
p = sys.argv[1]
base = [json.loads(x)['text'] for x in open(p, encoding='utf-8') if x.strip()]
t = p + '.tmp'
with open(t, 'w', encoding='utf-8') as f:
    n = 0
    for variant in range(5):
        for text in base:
            n += 1
            f.write(json.dumps({'text': f'case_id={n:03d}; {text} Variant={variant}.'}, ensure_ascii=False) + '\n')
os.replace(t, p)
PY
sha256sum "$WORKLOAD" > "$OUT/workload.sha256"

telemetry_start(){
  local file="$1"
  nvidia-smi --query-gpu=timestamp,name,temperature.gpu,utilization.gpu,utilization.memory,memory.used,power.draw,clocks.sm,clocks.mem \
    --format=csv -lms 500 > "$file" 2>&1 &
  TELE_PID=$!
}
telemetry_stop(){ kill "${TELE_PID:-}" >/dev/null 2>&1 || true; wait "${TELE_PID:-}" 2>/dev/null || true; TELE_PID=""; }

# Machine parser: AIPerf JSON summary + per-request JSONL. Zero errors remains exactly 0, never NA.
parse_run(){
  local artifact="$1" arm="$2" suite="$3" isl="$4" conc="$5" rep="$6" rc="$7" gpu="$8"
  python3 - "$artifact" "$arm" "$suite" "$isl" "$conc" "$rep" "$rc" "$gpu" "$MAX_ERROR_RATE" <<'PY'
import csv, json, os, re, sys
artifact, arm, suite, isl, conc, rep, rc, gpuf, maxerr = sys.argv[1:]
summary = os.path.join(artifact, 'profile_export_aiperf.json')
records = os.path.join(artifact, 'profile_export.jsonl')
try:
    d = json.load(open(summary, encoding='utf-8'))
except Exception:
    d = {}

def m(name, stat='avg'):
    x = d.get(name)
    if not isinstance(x, dict):
        return None
    v = x.get(stat)
    return float(v) if isinstance(v, (int, float)) else None

total = errors = 0
if os.path.exists(records):
    for line in open(records, encoding='utf-8', errors='replace'):
        try:
            r = json.loads(line)
        except Exception:
            continue
        md = r.get('metadata') or {}
        if md.get('benchmark_phase') not in (None, 'profiling'):
            continue
        total += 1
        if r.get('error') is not None:
            errors += 1
err = (100.0 * errors / total) if total else None
successful = (total - errors) if total else None
success_rate = (100.0 * successful / total) if total else None

parse_ok = bool(d) and total > 0
status = 'TIMEOUT' if int(rc) in (124, 137) else ('FAIL_AIPERF' if int(rc) != 0 else ('FAIL_PARSE' if not parse_ok else ('UNSTABLE' if err > float(maxerr) else 'PASS')))

mem = []; power = []; util = []; temp = []
try:
    rd = csv.reader(open(gpuf, encoding='utf-8', errors='replace')); next(rd, None)
    for row in rd:
        nums = []
        for s in row:
            z = re.search(r'-?\d+(?:\.\d+)?', s)
            nums.append(float(z.group()) if z else None)
        if len(nums) >= 7:
            if nums[2] is not None: temp.append(nums[2])
            if nums[3] is not None: util.append(nums[3])
            if nums[5] is not None: mem.append(nums[5])
            if nums[6] is not None: power.append(nums[6])
except Exception:
    pass

# GPU-side energy estimate: integrate sampled power over time.
# nvidia-smi samples at 500 ms (-lms 500). Approximate (includes warmup/cooldown
# and idle within the telemetry window); NOT full-system energy, NOT MLPerf Power.
SAMPLING_INTERVAL_S = 0.5
energy_j = (sum(power) * SAMPLING_INTERVAL_S) if power else None
j_per_req = (energy_j / successful) if (energy_j is not None and successful) else None
avg_out = m('output_sequence_length') or m('output_token_count')
total_out = (avg_out * successful) if (avg_out is not None and successful) else None
j_per_tok = (energy_j / total_out) if (energy_j is not None and total_out) else None

def f(x):
    return '' if x is None else f'{x:.4f}'
vals = [
    arm, suite, isl, conc, rep, status, f(err), str(total), str(successful), str(errors), f(success_rate),
    f(m('input_sequence_length')), f(m('output_sequence_length') or m('output_token_count')),
    f(m('time_to_first_token')), f(m('time_to_first_token', 'p50')), f(m('time_to_first_token', 'p95')), f(m('time_to_first_token', 'p99')),
    f(m('inter_token_latency')), f(m('inter_token_latency', 'p50')), f(m('inter_token_latency', 'p95')), f(m('inter_token_latency', 'p99')),
    f(m('request_latency')), f(m('request_latency', 'p50')), f(m('request_latency', 'p95')), f(m('request_latency', 'p99')),
    f(m('request_throughput')), f(m('output_token_throughput')),
    f(max(mem) if mem else None), f(max(power) if power else None), f(sum(util)/len(util) if util else None), f(max(temp) if temp else None),
    f(energy_j), f(j_per_req), f(j_per_tok),
]
print('\t'.join(vals))
PY
}

extract_error_details(){
  local artifact="$1" arm="$2" suite="$3" conc="$4" rep="$5"
  python3 - "$artifact" "$arm" "$suite" "$conc" "$rep" "$ERRORS" <<'PY'
import collections, json, os, re, sys
artifact, arm, suite, conc, rep, out = sys.argv[1:]
p = os.path.join(artifact, "profile_export.jsonl")
if not os.path.exists(p):
    raise SystemExit(0)

def flatten(x):
    if isinstance(x, str):
        return x
    try:
        return json.dumps(x, ensure_ascii=False, sort_keys=True)
    except Exception:
        return repr(x)

def classify(msg):
    checks = [
        ("ServerDisconnectedError", "ServerDisconnectedError"),
        ("ClientPayloadError", "ClientPayloadError"),
        ("TransferEncodingError", "TransferEncodingError"),
        ("ConnectionReset", "Connection reset by peer"),
        ("ClientOSError", "ClientOSError"),
        ("TimeoutError", "TimeoutError"),
        ("HTTPError", "HTTP"),
        ("ConnectionError", "Connection"),
    ]
    for label, pat in checks:
        if pat.lower() in msg.lower():
            return label
    m = re.search(r"([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))", msg)
    return m.group(1) if m else "OtherError"

counts = collections.Counter()
samples = {}
for line in open(p, encoding="utf-8", errors="replace"):
    try:
        r = json.loads(line)
    except Exception:
        continue
    md = r.get("metadata") or {}
    if md.get("benchmark_phase") not in (None, "profiling"):
        continue
    e = r.get("error")
    if e is None:
        continue
    msg = flatten(e).replace("\t", " ").replace("\n", " ")[:500]
    typ = classify(msg)
    counts[typ] += 1
    samples.setdefault(typ, msg)

with open(out, "a", encoding="utf-8") as f:
    for typ, n in sorted(counts.items()):
        sample = samples[typ]
        f.write(f"{arm}\t{suite}\t{conc}\t{rep}\t{typ}\t{n}\t{sample}\n")
PY
}

run_cell(){
  local arm="$1" suite="$2" isl="$3" conc="$4" rep="$5"
  local osl="${6:-$OUTPUT_TOKENS}"
  local dir="$OUT/$suite/$arm/isl_${isl}/c_${conc}/rep_${rep}"
  local artifact="$dir/artifacts"
  local gpu="$dir/gpu.csv"
  local console="$dir/aiperf.log"
  mkdir -p "$artifact"
  local events="$dir/docker-events.jsonl"
  log "$suite arm=$arm isl=$isl c=$conc rep=$rep"
  if ! start_arm "$arm" "$events"; then
    log "FATAL: startup failed during run: $arm"
    return 20
  fi

  curl -fsS "${URL[$arm]}/props" > "$dir/props.json" 2>/dev/null || true
  docker inspect "${CONTAINER[$arm]}" --format 'Image={{.Image}} Cmd={{json .Config.Cmd}}' > "$dir/container.txt" 2>&1 || true

  telemetry_start "$gpu"
  cmd=(aiperf profile
    --model "${MODEL[$arm]}"
    --url "${URL[$arm]}"
    --endpoint-type chat
    --streaming
    --connection-reuse-strategy "$CONNECTION_REUSE"
    --use-legacy-max-tokens
    --use-server-token-count
    --request-timeout-seconds "${REQUEST_TIMEOUT:-180}"
    --wait-for-model-timeout 10
    --wait-for-model-mode both
    --concurrency "$conc"
    --request-count "$REQUESTS"
    --warmup-request-count "$WARMUP"
    --random-seed "$SEED"
    --osl "$osl"
    --extra-inputs '{"temperature":0,"ignore_eos":true,"cache_prompt":false}'
    --artifact-dir "$artifact"
    --profile-export-level records
    --no-auto-plot)

  if [[ "$isl" == "raw" ]]; then
    cmd+=(--tokenizer builtin --input-file "$WORKLOAD" --custom-dataset-type single_turn --dataset-sampling-strategy sequential)
  else
    # Numeric ISL: synthetic token-controlled inputs via the reference tokenizer.
    cmd+=(--tokenizer Qwen/Qwen3-4B --apply-chat-template --isl "$isl")
  fi

  local t0 t1 elapsed row rc
  t0=$(date +%s)
  timeout --signal=TERM --kill-after=15s "${CELL_TIMEOUT:-900}s" "${cmd[@]}" > "$console" 2>&1
  rc=$?
  t1=$(date +%s)
  elapsed=$((t1-t0))
  telemetry_stop
  docker logs --timestamps --since "${CURRENT_START_EPOCH:-0}" "${CONTAINER[$arm]}" > "$dir/server.log" 2>&1 || true
  stop_event_capture
  row=$(parse_run "$artifact" "$arm" "$suite" "$isl" "$conc" "$rep" "$rc" "$gpu")
  extract_error_details "$artifact" "$arm" "$suite" "$conc" "$rep"
  printf '%s\n' "$row" >> "$ROWS"
  ROW_LAST="$row"
  status="$(printf '%s' "$row" | cut -f6)"
  log "DONE suite=$suite arm=$arm isl=$isl c=$conc rep=$rep status=$status elapsed=${elapsed}s rc=$rc"

  if (( rc != 0 )); then
    log "AIPERF FAILED. Last 120 lines from $console:"
    tail -n 120 "$console" >&2 || true
    docker logs --tail 120 "${CONTAINER[$arm]}" >&2 2>/dev/null || true
    docker stop "${CONTAINER[$arm]}" >/dev/null 2>&1 || true
    return "$rc"
  fi

  docker stop "${CONTAINER[$arm]}" >/dev/null 2>&1 || true
  sleep "$COOLDOWN_SECONDS"
  return 0
}

cat > "$SUMMARY" <<EOF2
Controlled MODEL diagnostic benchmark
Run=$RUN_ID Mode=$MODE
AIPerf=$(aiperf --version 2>&1 | head -n1)
GPU=$(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null | head -n1)
Requests=$REQUESTS Warmup=$WARMUP Repeats=$REPEATS OSL=$OUTPUT_TOKENS Seed=$SEED
Concurrency=${CONCURRENCIES[*]}

Primary comparison:
Spark-X2.5-4B-Q4_K_M vs Qwen3-4B-Q4_K_M

Controlled:
engine=llama.cpp
quantization=Q4_K_M
same GPU
same raw prompt bytes and order
same sampling parameters
same concurrency
same output-token cap

Independent variable:
model (checkpoint/architecture/tokenizer as one model package)

Primary report:
$REPORT
EOF2

printf 'arm\tsuite\tisl\tconcurrency\trepeat\tstatus\terror_rate_pct\tattempted_requests\tsuccessful_requests\tfailed_requests\tsuccess_rate_pct\tinput_tokens_avg\toutput_tokens_avg\tttft_avg_ms\tttft_p50_ms\tttft_p95_ms\tttft_p99_ms\titl_avg_ms\titl_p50_ms\titl_p95_ms\titl_p99_ms\tlatency_avg_ms\tlatency_p50_ms\tlatency_p95_ms\tlatency_p99_ms\trequest_tps\toutput_tps\tpeak_vram_mib\tpeak_power_w\tavg_gpu_util_pct\tpeak_temp_c\tgpu_energy_j\tgpu_j_per_request\tgpu_j_per_output_token\n' > "$ROWS"
printf 'arm\tsuite\tconcurrency\trepeat\terror_type\tcount\tsample\n' > "$ERRORS"

for arm in "${ALL_ARMS[@]}"; do
  docker inspect "${CONTAINER[$arm]}" >/dev/null 2>&1 || { echo "ERROR: ${CONTAINER[$arm]} missing. Run scripts/deploy.sh" >&2; exit 2; }
done

stop_all_models
preflight_config || exit 3
if [[ "$MODE" == "backend" ]]; then
  log "backend mode: same-engine runtime-control equivalence skipped (engines differ by design)"
else
  verify_runtime_controls || exit 5
fi

# AIPerf sanity gate: one actual request per model.
log "===== AIPerf sanity gate ====="
SANITY_REQUESTS="$REQUESTS"
SANITY_WARMUP="$WARMUP"
SANITY_OSL="$OUTPUT_TOKENS"
REQUESTS=1
WARMUP=1
OUTPUT_TOKENS=16
for arm in "${ALL_ARMS[@]}"; do
  log "sanity arm=$arm"
  if ! run_cell "$arm" sanity raw 1 0; then
    log "FATAL: AIPerf sanity failed for $arm. Full benchmark NOT started."
    exit 4
  fi
done
REQUESTS="$SANITY_REQUESTS"
WARMUP="$SANITY_WARMUP"
OUTPUT_TOKENS="$SANITY_OSL"
log "AIPerf sanity gate PASS for both models"

# ===== Benchmark v2: capacity suite (P2) =====
VRAM_LIMIT_MIB="${VRAM_LIMIT_MIB:-6000}"
THERMAL_LIMIT_C="${THERMAL_LIMIT_C:-85}"

write_v2_manifest() {
  local commit
  commit="$(cd "$ROOT" && git rev-parse HEAD 2>/dev/null || echo unknown)"
  python3 - "$OUT/manifest.json" "$MODE" "$RUN_ID" "$commit" "$WORKLOAD" <<'PY'
import json, os, sys, hashlib, datetime, subprocess
dst, mode, run_id, commit, workload = sys.argv[1:]
SPARK_SHA = "7934660bfc5b9bf04be0a0ac6179a1d16e1d4331b448857c86b8b2801b3ef72c"
QWEN_SHA = "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5"
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()
gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                      "--format=csv,noheader,nounits"],
                     capture_output=True, text=True).stdout.strip().split("\n")[0]
m = {
    "run_id": run_id,
    "mode": mode,
    "git_commit": commit,
    "models": ["Spark-X2.5-4B-Q4_K_M", "Qwen3-4B-Q4_K_M"],
    "model_sha256": {
        "Spark-X2.5-4B-Q4_K_M.gguf": SPARK_SHA,
        "Qwen3-4B-Q4_K_M.gguf": QWEN_SHA,
    },
    "aiperf_version": "0.12.0",
    "gpu": gpu,
    "serving_flags": ["--ctx-size", "9216", "--parallel", "4", "--cont-batching", "--metrics", "--n-gpu-layers", "999"],
    "workload_sha256": sha256_file(workload),
    "config": {
        "connection_reuse": os.environ.get("CONNECTION_REUSE", "never"),
        "temperature": 0, "ignore_eos": True, "cache_prompt": False,
        "requests_per_cell": os.environ.get("REQUESTS", "60"),
        "output_tokens": os.environ.get("OUTPUT_TOKENS", "128"),
        "seed": os.environ.get("SEED", "42"),
    },
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
json.dump(m, open(dst, "w", encoding="utf-8"), indent=2)
PY
  log "manifest=$OUT/manifest.json"
}

write_resource_summary() {
  python3 - "$ROWS" "$OUT/resource_summary.tsv" <<'PY'
import csv, sys
src, dst = sys.argv[1:]
rows = list(csv.DictReader(open(src, encoding="utf-8"), delimiter="\t"))
with open(dst, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, delimiter="\t")
    w.writerow(["arm", "suite", "isl", "concurrency", "repeat",
                "peak_vram_mib", "peak_power_w", "avg_gpu_util_pct", "peak_temp_c",
                "gpu_energy_j", "gpu_j_per_request", "gpu_j_per_output_token"])
    for r in rows:
        w.writerow([r["arm"], r["suite"], r["isl"], r["concurrency"], r["repeat"],
                    r["peak_vram_mib"], r["peak_power_w"], r["avg_gpu_util_pct"], r["peak_temp_c"],
                    r.get("gpu_energy_j", ""), r.get("gpu_j_per_request", ""),
                    r.get("gpu_j_per_output_token", "")])
PY
}

run_capacity() {
  local conc arm stop_reason="" concs
  # The capacity discovery must sweep even when the caller (open-loop/soak) did
  # not set CONCURRENCIES; fall back to the standard sweep.
  concs=("${CONCURRENCIES[@]}")
  [[ ${#concs[@]} -eq 0 ]] && concs=(1 2 3 4 6 8)
  for conc in "${concs[@]}"; do
    for arm in "${ALL_ARMS[@]}"; do
      run_cell "$arm" capacity raw "$conc" 1 || true
      local sr vram temp
      sr="$(printf '%s' "$ROW_LAST" | cut -f11)"
      vram="$(printf '%s' "$ROW_LAST" | cut -f28)"
      temp="$(printf '%s' "$ROW_LAST" | cut -f31)"
      log "capacity arm=$arm c=$conc success_rate=${sr}% vram=${vram}MiB temp=${temp}C"
      if awk "BEGIN{exit !($sr < $RELIABILITY_MIN_SUCCESS)}"; then
        stop_reason="RELIABILITY_STOP arm=$arm c=$conc success_rate=${sr}%"
      elif awk "BEGIN{exit !($vram >= $VRAM_LIMIT_MIB)}"; then
        stop_reason="VRAM_STOP arm=$arm c=$conc vram=${vram}MiB"
      elif awk "BEGIN{exit !($temp >= $THERMAL_LIMIT_C)}"; then
        stop_reason="THERMAL_STOP arm=$arm c=$conc temp=${temp}C"
      fi
      [[ -n "$stop_reason" ]] && break
    done
    [[ -n "$stop_reason" ]] && { log "STOP: $stop_reason"; break; }
  done
  if [[ -z "$stop_reason" ]]; then log "capacity sweep completed without a stop condition."; fi
  echo "stop_reason=${stop_reason:-NONE}" > "$OUT/capacity_stop.txt"
}

write_aggregate() {
  python3 - "$ROWS" "$OUT/aggregate.tsv" <<'PY'
import csv, math, statistics, sys
src, dst = sys.argv[1:]
rows = list(csv.DictReader(open(src, encoding='utf-8'), delimiter='\t'))
rows = [r for r in rows if r['suite'] not in ('sanity', 'smoke')]
keys = sorted({(r['suite'], r['arm'], r['isl'], r['concurrency']) for r in rows})
metrics = ['error_rate_pct','ttft_p50_ms','ttft_p95_ms','itl_p50_ms','itl_p95_ms','latency_p50_ms','latency_p95_ms','request_tps','output_tps','peak_vram_mib','peak_power_w']
with open(dst, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f, delimiter='\t')
    w.writerow(['suite','arm','isl','concurrency','pass_runs','unstable_runs','failed_runs','parsed_runs'] + [z for m in metrics for z in (m+'_mean', m+'_ci95')])
    for k in keys:
        rr = [r for r in rows if (r['suite'], r['arm'], r['isl'], r['concurrency']) == k]
        pass_r = [r for r in rr if r['status'] == 'PASS']
        unstable_r = [r for r in rr if r['status'] == 'UNSTABLE']
        parsed = pass_r + unstable_r
        failed_r = [r for r in rr if r['status'] not in ('PASS','UNSTABLE')]
        out = [*k, len(pass_r), len(unstable_r), len(failed_r), len(parsed)]
        for m in metrics:
            xs = [float(r[m]) for r in parsed if r.get(m,'') not in ('','NA')]
            if not xs:
                out += ['', '']; continue
            mean = statistics.mean(xs)
            if len(xs) == 1:
                ci = 0.0
            else:
                t95 = {2:12.706,3:4.303,4:3.182,5:2.776,6:2.571}
                ci = t95.get(len(xs)-1, 1.96) * statistics.stdev(xs) / math.sqrt(len(xs))
            out += [f'{mean:.4f}', f'{ci:.4f}']
        w.writerow(out)
PY
}

# Token-shape profiles are loaded from the canonical config (configs/benchmark.json)
# so the runner cannot drift from the report generator. ISL is controlled with the
# Qwen3-4B reference tokenizer (approximate for Spark-X2.5-4B, whose tokenizer
# differs). Max ISL is bounded by the serving config's per-slot context: the server
# runs --ctx-size 9216 --parallel 4 with a non-unified KV cache (2304 tokens per
# slot), and the Spark tokenizer inflates the Qwen-controlled ISL by ~2x.
eval "$(python3 - "$ROOT/configs/benchmark.json" <<'PY'
import json, sys
sp = json.load(open(sys.argv[1], encoding="utf-8"))["shape_profiles"]
print('SHAPE_PROFILE_ORDER="' + " ".join(sp["order"]) + '"')
print("declare -A SHAPE_PROFILES=(")
for name, p in sp["profiles"].items():
    print(f'  [{name}]="{p["isl"]} {p["osl"]}"')
print(")")
PY
)"

run_shape() {
  local profile isl osl conc arm spec
  for profile in $SHAPE_PROFILE_ORDER; do
    read -r isl osl <<< "${SHAPE_PROFILES[$profile]}"
    for conc in "${CONCURRENCIES[@]}"; do
      for arm in "${ALL_ARMS[@]}"; do
        run_cell "$arm" "shape_${profile}" "$isl" "$conc" 1 "$osl" || true
        log "shape profile=$profile isl=$isl osl=$osl arm=$arm c=$conc"
      done
    done
  done
}

# ===== P4 open-loop + goodput =====
# Reference SLO profiles (DistServe-style goodput; NOT MLPerf compliance):
#   interactive-reference: TTFT<=500ms, TPOT<=30ms
#   server-reference:      TTFT<=2000ms, TPOT<=100ms
SLO_TTFT_INTERACTIVE="${SLO_TTFT_INTERACTIVE:-500}"
SLO_TPOT_INTERACTIVE="${SLO_TPOT_INTERACTIVE:-30}"
SLO_TTFT_SERVER="${SLO_TTFT_SERVER:-2000}"
SLO_TPOT_SERVER="${SLO_TPOT_SERVER:-100}"
OPEN_LOOP_FRACTIONS="${OPEN_LOOP_FRACTIONS:-0.25 0.5 0.75 0.9 1.0 1.1}"
OPEN_LOOP_BASE_RPS="${OPEN_LOOP_BASE_RPS:-}"
OPEN_LOOP_REQUESTS="${OPEN_LOOP_REQUESTS:-200}"
MAX_OPEN_CONC="${MAX_OPEN_CONC:-16}"

run_openloop_cell() {
  local arm="$1" rate="$2" conc="$3" label="$4"
  local dir="$OUT/openloop/$arm/$label"
  local artifact="$dir/artifacts"
  local gpu="$dir/gpu.csv"
  local console="$dir/aiperf.log"
  mkdir -p "$artifact"
  local events="$dir/docker-events.jsonl"
  log "openloop arm=$arm rate=$rate cap=$conc label=$label"
  if ! start_arm "$arm" "$events"; then
    log "FATAL: startup failed during run: $arm"
    return 20
  fi
  telemetry_start "$gpu"
  cmd=(aiperf profile
    --model "${MODEL[$arm]}"
    --url "${URL[$arm]}"
    --endpoint-type chat
    --streaming
    --connection-reuse-strategy "$CONNECTION_REUSE"
    --use-legacy-max-tokens
    --use-server-token-count
    --request-timeout-seconds "${REQUEST_TIMEOUT:-180}"
    --wait-for-model-timeout 10
    --wait-for-model-mode both
    --request-rate "$rate"
    --arrival-pattern poisson
    --concurrency "$conc"
    --request-count "$OPEN_LOOP_REQUESTS"
    --warmup-request-count "$WARMUP"
    --random-seed "$SEED"
    --osl "$OUTPUT_TOKENS"
    --extra-inputs '{"temperature":0,"ignore_eos":true,"cache_prompt":false}'
    --artifact-dir "$artifact"
    --profile-export-level records
    --no-auto-plot
    --tokenizer builtin
    --input-file "$WORKLOAD" --custom-dataset-type single_turn --dataset-sampling-strategy sequential)
  local rc row
  timeout --signal=TERM --kill-after=15s "${CELL_TIMEOUT:-900}s" "${cmd[@]}" > "$console" 2>&1
  rc=$?
  telemetry_stop
  docker logs --timestamps --since "${CURRENT_START_EPOCH:-0}" "${CONTAINER[$arm]}" > "$dir/server.log" 2>&1 || true
  stop_event_capture
  row=$(parse_run "$artifact" "$arm" "openloop" "raw" "$conc" "1" "$rc" "$gpu")
  extract_error_details "$artifact" "$arm" "openloop" "$conc" "1"
  printf '%s\n' "$row" >> "$ROWS"
  ROW_LAST="$row"
  printf '%s\t%s\t%s\t%s\t%s\n' "$arm" "$label" "$rate" "$conc" "$artifact" >> "$OUT/openloop_cells.tsv"
  docker stop "${CONTAINER[$arm]}" >/dev/null 2>&1 || true
  sleep "$COOLDOWN_SECONDS"
  return 0
}

write_slo_summary() {
  python3 - "$OUT/openloop_cells.tsv" "$OUT/slo_summary.tsv" \
    "$SLO_TTFT_INTERACTIVE" "$SLO_TPOT_INTERACTIVE" "$SLO_TTFT_SERVER" "$SLO_TPOT_SERVER" <<'PY'
import csv, json, os, sys
cells, dst, ittft, itpot, sttft, stpot = sys.argv[1:7]
slo_profiles = [
    ("interactive", float(ittft), float(itpot)),
    ("server", float(sttft), float(stpot)),
]
agg = {}   # (arm, label, rate, profile) -> [compliant, attempted]
dur = {}   # (arm, label, rate) -> benchmark duration in seconds
for line in open(cells, encoding='utf-8'):
    parts = line.rstrip('\n').split('\t')
    if len(parts) < 5:
        continue
    arm, label, rate, conc, artifact = parts[:5]
    rec = os.path.join(artifact, 'profile_export.jsonl')
    starts = []
    ends = []
    for l in open(rec, encoding='utf-8', errors='replace'):
        try:
            r = json.loads(l)
        except Exception:
            continue
        md = r.get('metadata') or {}
        if md.get('benchmark_phase') not in (None, 'profiling'):
            continue
        if md.get('request_start_ns'):
            starts.append(md['request_start_ns'])
        if md.get('request_end_ns'):
            ends.append(md['request_end_ns'])
        e = r.get('error')
        m = r.get('metrics') or {}
        ttft = (m.get('time_to_first_token') or {}).get('value')
        itl = (m.get('inter_token_latency') or {}).get('value')
        for name, t, p in slo_profiles:
            key = (arm, label, rate, name)
            a = agg.setdefault(key, [0, 0])
            a[1] += 1   # attempted
            if e is None and ttft is not None and itl is not None and ttft <= t and itl <= p:
                a[0] += 1   # compliant
    if starts and ends:
        dur[(arm, label, rate)] = (max(ends) - min(starts)) / 1e9
with open(dst, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f, delimiter='\t')
    w.writerow(['arm', 'load_fraction', 'target_rate_rps', 'slo_profile', 'attempted', 'slo_compliant', 'good_request_fraction', 'goodput_req_s'])
    for (arm, label, rate, prof), (ok, tot) in sorted(agg.items()):
        frac = 0.0 if tot == 0 else ok / tot
        d = dur.get((arm, label, rate), 0.0)
        goodput = (ok / d) if d > 0 else 0.0
        w.writerow([arm, label, rate, prof, tot, ok, f'{frac:.4f}', f'{goodput:.4f}'])
print(f'slo_summary written: {len(agg)} rows')
PY
}

run_openloop() {
  local base conc frac rate arm
  conc="$MAX_OPEN_CONC"
  if [[ -z "$OPEN_LOOP_BASE_RPS" ]]; then
    # Derive R from a quick capacity discovery run (max stable request_tps).
    log "OPEN_LOOP_BASE_RPS unset; running capacity discovery to derive R"
    run_capacity
    base=$(python3 - "$ROWS" <<'PY'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1], encoding='utf-8'), delimiter='\t'))
vals = [float(r['request_tps']) for r in rows
        if r['suite'] == 'capacity' and r.get('request_tps') not in ('', 'NA')]
print(max(vals) if vals else '0')
PY
)
  else
    base="$OPEN_LOOP_BASE_RPS"
  fi
  log "open-loop base rate R=${base} req/s, fractions: ${OPEN_LOOP_FRACTIONS}"
  for frac in $OPEN_LOOP_FRACTIONS; do
    rate=$(python3 -c "print(f'{float('$base') * float('$frac'):.4f}')")
    label="f${frac}"
    for arm in "${ALL_ARMS[@]}"; do
      run_openloop_cell "$arm" "$rate" "$conc" "$label" || true
    done
  done
}

if [[ "$MODE" == "capacity" ]]; then
  log "===== CAPACITY benchmark (closed-loop adaptive sweep) ====="
  run_capacity
  write_resource_summary
  write_aggregate
  write_v2_manifest
  log "===== capacity complete ====="
  log "repeats=$ROWS"
  log "aggregate=$OUT/aggregate.tsv"
  log "resource_summary=$OUT/resource_summary.tsv"
  log "manifest=$OUT/manifest.json"
  exit 0
fi

if [[ "$MODE" == "shape" ]]; then
  log "===== SHAPE benchmark (token ISL/OSL profiles) ====="
  run_shape
  write_resource_summary
  write_aggregate
  write_v2_manifest
  log "===== shape complete ====="
  log "repeats=$ROWS"
  log "aggregate=$OUT/aggregate.tsv"
  log "resource_summary=$OUT/resource_summary.tsv"
  log "manifest=$OUT/manifest.json"
  exit 0
fi

if [[ "$MODE" == "open-loop" ]]; then
  log "===== OPEN-LOOP benchmark (Poisson arrival + goodput/SLO) ====="
  run_openloop
  write_resource_summary
  write_aggregate
  write_slo_summary
  write_v2_manifest
  log "===== open-loop complete ====="
  log "repeats=$ROWS"
  log "aggregate=$OUT/aggregate.tsv"
  log "resource_summary=$OUT/resource_summary.tsv"
  log "slo_summary=$OUT/slo_summary.tsv"
  log "manifest=$OUT/manifest.json"
  exit 0
fi

# ===== P5 startup + soak =====
STARTUP_REPEATS="${STARTUP_REPEATS:-3}"
SOAK_DURATION="${SOAK_DURATION:-600}"
SOAK_LOAD_FRACTION="${SOAK_LOAD_FRACTION:-0.75}"
SOAK_BASE_RPS="${SOAK_BASE_RPS:-}"
SOAK_SLICE="${SOAK_SLICE:-30}"

run_startup() {
  local arm c url t0 t1 ttft rep api_ready_ms first_token_ms deadline
  printf 'arm\trep\tprocess_to_api_ready_ms\tapi_ready_to_first_token_ms\n' > "$OUT/startup.tsv"
  for arm in "${ALL_ARMS[@]}"; do
    c="${CONTAINER[$arm]}"; url="${URL[$arm]}"
    for rep in $(seq 1 "$STARTUP_REPEATS"); do
      docker stop "$c" >/dev/null 2>&1 || true
      sleep 2
      t0=$(date +%s%3N)
      docker start "$c" >/dev/null 2>&1
      deadline=$(( $(date +%s) + STARTUP_TIMEOUT ))
      api_ready_ms=""
      while :; do
        if curl -fsS --max-time 2 "$url/v1/models" >/dev/null 2>&1; then
          t1=$(date +%s%3N)
          api_ready_ms=$((t1-t0))
          break
        fi
        [[ $(date +%s) -ge $deadline ]] && break
        sleep 0.5
      done
      first_token_ms=""
      if [[ -n "$api_ready_ms" ]]; then
        ttft=$(curl -sN --max-time 120 -w '%{time_starttransfer}' -o /dev/null \
          "$url/v1/chat/completions" \
          -H 'Content-Type: application/json' \
          -d "{\"model\":\"${MODEL[$arm]}\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hello.\"}],\"stream\":true,\"max_tokens\":16,\"temperature\":0}" 2>/dev/null)
        first_token_ms=$(awk "BEGIN{printf \"%.1f\", $ttft*1000}" 2>/dev/null || echo "")
      fi
      printf '%s\t%d\t%s\t%s\n' "$arm" "$rep" "${api_ready_ms:-}" "$first_token_ms" >> "$OUT/startup.tsv"
      log "startup arm=$arm rep=$rep api_ready=${api_ready_ms:-FAIL}ms first_token=${first_token_ms:-}ms"
      docker stop "$c" >/dev/null 2>&1 || true
    done
  done
}

run_soak_cell() {
  local arm="$1" rate="$2" conc="$3" duration="$4"
  local dir="$OUT/soak/$arm"
  local artifact="$dir/artifacts"
  local gpu="$dir/gpu.csv"
  local console="$dir/aiperf.log"
  mkdir -p "$artifact"
  local events="$dir/docker-events.jsonl"
  log "soak arm=$arm rate=$rate cap=$conc duration=${duration}s"
  if ! start_arm "$arm" "$events"; then
    log "FATAL: startup failed during soak: $arm"
    return 20
  fi
  telemetry_start "$gpu"
  cmd=(aiperf profile
    --model "${MODEL[$arm]}"
    --url "${URL[$arm]}"
    --endpoint-type chat
    --streaming
    --connection-reuse-strategy "$CONNECTION_REUSE"
    --use-legacy-max-tokens
    --use-server-token-count
    --request-timeout-seconds "${REQUEST_TIMEOUT:-180}"
    --wait-for-model-timeout 10
    --wait-for-model-mode both
    --request-rate "$rate"
    --arrival-pattern poisson
    --concurrency "$conc"
    --benchmark-duration "$duration"
    --slice-duration "$SOAK_SLICE"
    --warmup-request-count "$WARMUP"
    --random-seed "$SEED"
    --osl "$OUTPUT_TOKENS"
    --extra-inputs '{"temperature":0,"ignore_eos":true,"cache_prompt":false}'
    --artifact-dir "$artifact"
    --profile-export-level records
    --no-auto-plot
    --tokenizer builtin
    --input-file "$WORKLOAD" --custom-dataset-type single_turn --dataset-sampling-strategy sequential)
  local rc row
  timeout --signal=TERM --kill-after=15s "$((duration + 120))s" "${cmd[@]}" > "$console" 2>&1
  rc=$?
  telemetry_stop
  docker logs --timestamps --since "${CURRENT_START_EPOCH:-0}" "${CONTAINER[$arm]}" > "$dir/server.log" 2>&1 || true
  stop_event_capture
  row=$(parse_run "$artifact" "$arm" "soak" "raw" "$conc" "1" "$rc" "$gpu")
  extract_error_details "$artifact" "$arm" "soak" "$conc" "1"
  printf '%s\n' "$row" >> "$ROWS"
  ROW_LAST="$row"
  printf '%s\t%s\t%s\t%s\t%s\n' "$arm" "$rate" "$duration" "$dir" "$artifact" >> "$OUT/soak_cells.tsv"
  docker stop "${CONTAINER[$arm]}" >/dev/null 2>&1 || true
  sleep "$COOLDOWN_SECONDS"
  return 0
}

write_soak_summary() {
  python3 - "$OUT/soak_cells.tsv" "$OUT/soak_summary.tsv" <<'PY'
import csv, re, sys
cells, dst = sys.argv[1:]
def num(s):
    m = re.search(r'-?\d+(?:\.\d+)?', s)
    return float(m.group()) if m else None
with open(dst, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f, delimiter='\t')
    w.writerow(['arm', 'duration_s', 'temp_min_c', 'temp_mean_c', 'temp_max_c',
                'power_mean_w', 'power_max_w', 'util_mean_pct', 'util_max_pct',
                'sm_clock_min_mhz', 'sm_clock_max_mhz', 'sm_clock_drop_pct', 'throttled'])
    for line in open(cells, encoding='utf-8'):
        parts = line.rstrip('\n').split('\t')
        if len(parts) < 5:
            continue
        arm, rate, duration, d, artifact = parts[:5]
        gpu = f'{d}/gpu.csv'
        temps, powers, utils, smclocks = [], [], [], []
        try:
            rd = csv.reader(open(gpu, encoding='utf-8', errors='replace')); next(rd, None)
            for row in rd:
                # columns: timestamp, name, temp, gpu_util, mem_util, mem_used, power, sm_clock, mem_clock
                vals = [num(x) for x in row]
                if len(vals) >= 8:
                    if vals[2] is not None: temps.append(vals[2])     # temperature.gpu
                    if vals[3] is not None: utils.append(vals[3])     # utilization.gpu
                    if vals[6] is not None: powers.append(vals[6])    # power.draw
                    if vals[7] is not None: smclocks.append(vals[7])  # clocks.current.sm
        except Exception:
            pass
        def stat(xs):
            if not xs: return ('', '', '')
            return (f'{min(xs):.1f}', f'{sum(xs)/len(xs):.1f}', f'{max(xs):.1f}')
        tmin, tmean, tmax = stat(temps)
        _, pmean, pmax = stat(powers)
        _, umean, umax = stat(utils)
        smin, _, smax = stat(smclocks)
        drop = 0.0
        if smclocks:
            mn, mx = min(smclocks), max(smclocks)
            drop = 0.0 if mx == 0 else (mx - mn) / mx * 100.0
        throttled = (drop > 10.0 and temps and max(temps) >= 85.0)
        w.writerow([arm, duration, tmin, tmean, tmax, pmean, pmax, umean, umax, smin, smax, f'{drop:.1f}', 'yes' if throttled else 'no'])
print('soak_summary written')
PY
}

run_soak() {
  local base conc rate
  conc="$MAX_OPEN_CONC"
  if [[ -z "$SOAK_BASE_RPS" ]]; then
    log "SOAK_BASE_RPS unset; running capacity discovery to derive R"
    run_capacity
    base=$(python3 - "$ROWS" <<'PY'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1], encoding='utf-8'), delimiter='\t'))
vals = [float(r['request_tps']) for r in rows
        if r['suite'] == 'capacity' and r.get('request_tps') not in ('', 'NA')]
print(max(vals) if vals else '0')
PY
)
  else
    base="$SOAK_BASE_RPS"
  fi
  rate=$(python3 -c "print(f'{float('$base') * float('$SOAK_LOAD_FRACTION'):.4f}')")
  log "soak base rate R=${base} req/s, load=${SOAK_LOAD_FRACTION} -> rate=${rate} req/s, duration=${SOAK_DURATION}s"
  for arm in "${ALL_ARMS[@]}"; do
    run_soak_cell "$arm" "$rate" "$conc" "$SOAK_DURATION" || true
  done
}

if [[ "$MODE" == "startup" ]]; then
  log "===== STARTUP benchmark (process cold start) ====="
  run_startup
  write_v2_manifest
  log "===== startup complete ====="
  log "startup=$OUT/startup.tsv"
  log "manifest=$OUT/manifest.json"
  exit 0
fi

if [[ "$MODE" == "soak" ]]; then
  log "===== SOAK benchmark (sustained load + thermal degradation) ====="
  run_soak
  write_resource_summary
  write_aggregate
  write_soak_summary
  write_v2_manifest
  log "===== soak complete ====="
  log "repeats=$ROWS"
  log "aggregate=$OUT/aggregate.tsv"
  log "soak_summary=$OUT/soak_summary.tsv"
  log "manifest=$OUT/manifest.json"
  exit 0
fi

# ===== P7 sessions + prefix-cache experiment =====
SESSIONS_CONVERSATIONS="${SESSIONS_CONVERSATIONS:-20}"
SESSIONS_TURNS="${SESSIONS_TURNS:-4}"
SESSIONS_CACHE="${SESSIONS_CACHE:-0}"

run_sessions_cell() {
  local arm="$1" cache="$2"
  local tag="nocache"; [[ "$cache" == "true" ]] && tag="cache"
  local dir="$OUT/sessions/$arm/$tag"
  local artifact="$dir/artifacts"
  local gpu="$dir/gpu.csv"
  local console="$dir/aiperf.log"
  mkdir -p "$artifact"
  local events="$dir/docker-events.jsonl"
  log "sessions arm=$arm cache_prompt=$cache"
  if ! start_arm "$arm" "$events"; then
    log "FATAL: startup failed during sessions: $arm"
    return 20
  fi
  telemetry_start "$gpu"
  cmd=(aiperf profile
    --model "${MODEL[$arm]}"
    --url "${URL[$arm]}"
    --endpoint-type chat
    --streaming
    --connection-reuse-strategy "$CONNECTION_REUSE"
    --use-legacy-max-tokens
    --use-server-token-count
    --request-timeout-seconds "${REQUEST_TIMEOUT:-180}"
    --wait-for-model-timeout 10
    --wait-for-model-mode both
    --concurrency 1
    --request-count "$REQUESTS"
    --warmup-request-count "$WARMUP"
    --random-seed "$SEED"
    --osl "$OUTPUT_TOKENS"
    --extra-inputs "{\"temperature\":0,\"ignore_eos\":true,\"cache_prompt\":$cache}"
    --conversation-num "$SESSIONS_CONVERSATIONS"
    --conversation-turn-mean "$SESSIONS_TURNS"
    --conversation-turn-delay-mean 0
    --artifact-dir "$artifact"
    --profile-export-level records
    --no-auto-plot
    --tokenizer builtin)
  local rc row
  timeout --signal=TERM --kill-after=15s "${CELL_TIMEOUT:-900}s" "${cmd[@]}" > "$console" 2>&1
  rc=$?
  telemetry_stop
  docker logs --timestamps --since "${CURRENT_START_EPOCH:-0}" "${CONTAINER[$arm]}" > "$dir/server.log" 2>&1 || true
  stop_event_capture
  row=$(parse_run "$artifact" "$arm" "sessions" "raw" "1" "1" "$rc" "$gpu")
  extract_error_details "$artifact" "$arm" "sessions" "1" "1"
  printf '%s\n' "$row" >> "$ROWS"
  ROW_LAST="$row"
  printf '%s\t%s\t%s\n' "$arm" "$cache" "$artifact" >> "$OUT/sessions_cells.tsv"
  docker stop "${CONTAINER[$arm]}" >/dev/null 2>&1 || true
  sleep "$COOLDOWN_SECONDS"
  return 0
}

write_sessions_summary() {
  python3 - "$OUT/sessions_cells.tsv" "$OUT/sessions.tsv" <<'PY'
import csv, json, os, statistics, sys
cells, dst = sys.argv[1:]
agg = {}   # (arm, cache, turn) -> [ttft, ...]
for line in open(cells, encoding='utf-8'):
    parts = line.rstrip('\n').split('\t')
    if len(parts) < 3:
        continue
    arm, cache, artifact = parts[:3]
    rec = os.path.join(artifact, 'profile_export.jsonl')
    for l in open(rec, encoding='utf-8', errors='replace'):
        try:
            r = json.loads(l)
        except Exception:
            continue
        md = r.get('metadata') or {}
        if md.get('benchmark_phase') not in (None, 'profiling'):
            continue
        if r.get('error') is not None:
            continue
        turn = md.get('turn_index')
        m = r.get('metrics') or {}
        ttft = (m.get('time_to_first_token') or {}).get('value')
        if ttft is not None and turn is not None:
            agg.setdefault((arm, cache, turn), []).append(ttft)
with open(dst, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f, delimiter='\t')
    w.writerow(['arm', 'cache_prompt', 'turn', 'requests', 'ttft_mean_ms', 'ttft_p50_ms'])
    for (arm, cache, turn), xs in sorted(agg.items()):
        w.writerow([arm, cache, turn, len(xs), f'{statistics.mean(xs):.2f}', f'{statistics.median(xs):.2f}'])
print(f'sessions_summary written: {len(agg)} rows')
PY
}

run_sessions() {
  local arm
  for arm in "${ALL_ARMS[@]}"; do
    run_sessions_cell "$arm" "false" || true
    if [[ "$SESSIONS_CACHE" == "1" ]]; then
      run_sessions_cell "$arm" "true" || true
    fi
  done
}

if [[ "$MODE" == "sessions" ]]; then
  log "===== SESSIONS benchmark (multi-turn, latency by turn) ====="
  run_sessions
  write_resource_summary
  write_aggregate
  write_sessions_summary
  write_v2_manifest
  log "===== sessions complete ====="
  log "repeats=$ROWS"
  log "aggregate=$OUT/aggregate.tsv"
  log "sessions=$OUT/sessions.tsv"
  log "manifest=$OUT/manifest.json"
  exit 0
fi

# ===== P8 backend comparison (same Qwen GGUF on llama.cpp vs vLLM+GGUF) =====
run_backend() {
  local conc rep A B
  for conc in "${CONCURRENCIES[@]}"; do
    for rep in $(seq 1 "$REPEATS"); do
      if (( rep % 2 )); then A=qwen_llama; B=qwen_vllm_gguf; else A=qwen_vllm_gguf; B=qwen_llama; fi
      run_cell "$A" backend raw "$conc" "$rep" || exit $?
      run_cell "$B" backend raw "$conc" "$rep" || exit $?
    done
  done
}

if [[ "$MODE" == "backend" ]]; then
  log "===== BACKEND benchmark (llama.cpp vs vLLM+GGUF, same Qwen GGUF) ====="
  run_backend
  write_resource_summary
  write_aggregate
  write_v2_manifest
  log "===== backend complete ====="
  log "repeats=$ROWS"
  log "aggregate=$OUT/aggregate.tsv"
  log "resource_summary=$OUT/resource_summary.tsv"
  log "manifest=$OUT/manifest.json"
  exit 0
fi

if [[ "$MODE" == "smoke" ]]; then
  log "===== smoke: model comparison pipeline ====="
  for arm in "${ALL_ARMS[@]}"; do
    run_cell "$arm" smoke raw 1 1 || exit $?
  done
  log "===== smoke complete ====="
  log "raw=$ROWS"
  exit 0
fi

# final -> model comparison matrix; reliability -> P0 transport-reliability gate.
if [[ "$MODE" == "reliability" ]]; then
  SUITE="reliability"
  log "===== RELIABILITY benchmark (P0 gate) ====="
else
  SUITE="model"
  log "===== MODEL benchmark ====="
fi

# Crossover ordering alternates A/B by repeat to reduce temporal/thermal order bias.
for conc in "${CONCURRENCIES[@]}"; do
  for rep in $(seq 1 "$REPEATS"); do
    if (( rep % 2 )); then
      A=spark_llama; B=qwen_llama
    else
      A=qwen_llama; B=spark_llama
    fi
    run_cell "$A" "$SUITE" raw "$conc" "$rep" || exit $?
    run_cell "$B" "$SUITE" raw "$conc" "$rep" || exit $?
  done
done

# Aggregate successfully parsed runs.
python3 - "$ROWS" "$OUT/aggregate.tsv" <<'PY'
import csv, math, statistics, sys
src, dst = sys.argv[1:]
rows = list(csv.DictReader(open(src, encoding='utf-8'), delimiter='\t'))
keys = sorted({(r['suite'], r['arm'], r['isl'], r['concurrency']) for r in rows})
metrics = ['error_rate_pct','ttft_p50_ms','ttft_p95_ms','itl_p50_ms','itl_p95_ms','latency_p50_ms','latency_p95_ms','request_tps','output_tps','peak_vram_mib','peak_power_w']
with open(dst, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f, delimiter='\t')
    w.writerow(['suite','arm','isl','concurrency','pass_runs','unstable_runs','failed_runs','parsed_runs'] + [z for m in metrics for z in (m+'_mean', m+'_ci95')])
    for k in keys:
        rr = [r for r in rows if (r['suite'], r['arm'], r['isl'], r['concurrency']) == k]
        pass_r = [r for r in rr if r['status'] == 'PASS']
        unstable_r = [r for r in rr if r['status'] == 'UNSTABLE']
        parsed = pass_r + unstable_r   # successfully parsed repeats
        failed_r = [r for r in rr if r['status'] not in ('PASS','UNSTABLE')]
        out = [*k, len(pass_r), len(unstable_r), len(failed_r), len(parsed)]
        for m in metrics:
            xs = [float(r[m]) for r in parsed if r.get(m,'') not in ('','NA')]
            if not xs:
                out += ['', '']; continue
            mean = statistics.mean(xs)
            if len(xs) == 1:
                ci = 0.0
            else:
                t95 = {1:12.706,2:4.303,3:3.182,4:2.776,5:2.571,6:2.447,7:2.365,8:2.306,9:2.262,10:2.228}
                ci = t95.get(len(xs)-1, 1.96) * statistics.stdev(xs) / math.sqrt(len(xs))
            out += [f'{mean:.4f}', f'{ci:.4f}']
        w.writerow(out)
PY

# Reliability hard gate (P0). A publication-grade final/reliability run must
# meet the transport success threshold; otherwise it is refused unless
# FORCE_UNSTABLE=1, in which case it is explicitly marked INVALID_FOR_RANKING.
if [[ "$MODE" == "final" || "$MODE" == "reliability" ]]; then
  GATE=$(python3 - "$ROWS" "$RELIABILITY_MIN_SUCCESS" <<'PY'
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1], encoding='utf-8'), delimiter='\t'))
rows = [r for r in rows if r['suite'] in ('model', 'reliability')]
attempted = sum(int(r['attempted_requests']) for r in rows if r.get('attempted_requests','').isdigit())
failed = sum(int(r['failed_requests']) for r in rows if r.get('failed_requests','').isdigit())
rate = 100.0 * (attempted - failed) / attempted if attempted else 0.0
print(f'{attempted} {failed} {rate:.4f}')
PY
)
  read -r GATE_ATTEMPTED GATE_FAILED GATE_RATE <<< "$GATE"
  log "Reliability gate: attempted=$GATE_ATTEMPTED failed=$GATE_FAILED success_rate=${GATE_RATE}% (threshold ${RELIABILITY_MIN_SUCCESS}%)"
  if awk "BEGIN{exit !($GATE_RATE < $RELIABILITY_MIN_SUCCESS)}"; then
    if [[ "$FORCE_UNSTABLE" == "1" ]]; then
      echo "INVALID_FOR_RANKING" > "$OUT/validity.txt"
      log "WARN: success rate below gate but FORCE_UNSTABLE=1 — run marked INVALID_FOR_RANKING."
    else
      echo "RELIABILITY_FAILED" > "$OUT/validity.txt"
      log "FATAL: transport success rate ${GATE_RATE}% is below the ${RELIABILITY_MIN_SUCCESS}% reliability gate."
      log "       Refusing to produce a final ranking. CONNECTION_REUSE defaults to 'never'."
      log "       To force anyway: FORCE_UNSTABLE=1 MODE=$MODE ./scripts/benchmark.sh"
      exit 7
    fi
  else
    echo "RELIABILITY_PASS" > "$OUT/validity.txt"
    log "Reliability gate PASS."
  fi
fi

if [[ "$MODE" == "reliability" ]]; then
  cat > "$OUT/summary.txt.reliability" <<EOF
Transport reliability gate result
Run=$RUN_ID Mode=$MODE
attempted_requests=$GATE_ATTEMPTED
failed_requests=$GATE_FAILED
success_rate_pct=$GATE_RATE
threshold_pct=$RELIABILITY_MIN_SUCCESS
validity=$(cat "$OUT/validity.txt")
connection_reuse=$CONNECTION_REUSE
EOF
  log "===== reliability complete ====="
  log "raw=$ROWS"
  log "aggregate=$OUT/aggregate.tsv"
  exit 0
fi

# Generate the primary human-readable side-by-side report.
SPARK_GGUF="$MODEL_DIR/Spark-X2.5-4B-Q4_K_M.gguf"
QWEN_GGUF="$MODEL_DIR/Qwen3-4B-Q4_K_M.gguf"
SPARK_SHA="$(sha256sum "$SPARK_GGUF" 2>/dev/null | awk '{print $1}' || true)"
QWEN_SHA="$(sha256sum "$QWEN_GGUF" 2>/dev/null | awk '{print $1}' || true)"
GPU_DESC="$(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null | head -n1)"
HOST_DESC="$(uname -srmo 2>/dev/null || uname -a)"

python3 - "$ROWS" "$REPORT" "$RUN_ID" "$REQUESTS" "$WARMUP" "$REPEATS" "$OUTPUT_TOKENS" \
  "${CONCURRENCIES[*]}" "$GPU_DESC" "$HOST_DESC" "$SPARK_SHA" "$QWEN_SHA" <<'PY'
import csv, math, statistics, sys
(src, dst, run_id, requests, warmup, repeats, osl, concs,
 gpu_desc, host_desc, spark_sha, qwen_sha) = sys.argv[1:]

rows = list(csv.DictReader(open(src, encoding="utf-8"), delimiter="\t"))
rows = [r for r in rows if r["suite"] == "model"]

arms = {
    "spark_llama": "Spark-X2.5-4B Q4_K_M",
    "qwen_llama": "Qwen3-4B Q4_K_M",
}
metrics = [
    ("error_rate_pct", "Error rate", "%", "lower", True),
    ("ttft_p50_ms", "TTFT p50", "ms", "lower", True),
    ("ttft_p95_ms", "TTFT p95", "ms", "lower", True),
    ("itl_p50_ms", "ITL p50", "ms", "lower", True),
    ("itl_p95_ms", "ITL p95", "ms", "lower", True),
    ("latency_p50_ms", "E2E latency p50", "ms", "lower", True),
    ("latency_p95_ms", "E2E latency p95", "ms", "lower", True),
    ("request_tps", "Request throughput", "req/s", "higher", True),
    ("output_tps", "Output throughput*", "tok/s", "higher", False),
    ("peak_vram_mib", "Peak VRAM", "MiB", "lower", False),
    ("peak_power_w", "Peak power", "W", "lower", False),
]

def tcrit(n):
    if n <= 1:
        return 0.0
    table = {2:12.706, 3:4.303, 4:3.182, 5:2.776, 6:2.571,
             7:2.447, 8:2.365, 9:2.306, 10:2.262, 11:2.228}
    return table.get(n, 1.96)

def stats(arm, conc, metric):
    rr = [r for r in rows if r["arm"] == arm and r["concurrency"] == str(conc)]
    rr = [r for r in rr if r["status"] in ("PASS", "UNSTABLE")]
    xs = []
    for r in rr:
        v = r.get(metric, "")
        if v not in ("", "NA"):
            try:
                xs.append(float(v))
            except Exception:
                pass
    if not xs:
        return None, None, 0
    mean = statistics.mean(xs)
    ci = 0.0 if len(xs) == 1 else tcrit(len(xs)) * statistics.stdev(xs) / math.sqrt(len(xs))
    return mean, ci, len(xs)

def fmt(mean, ci, unit):
    if mean is None:
        return "NA"
    if unit == "%":
        return f"{mean:.2f}% ± {ci:.2f}"
    if unit in ("ms", "MiB", "W"):
        return f"{mean:.2f} ± {ci:.2f}"
    return f"{mean:.3f} ± {ci:.3f}"

def delta(a, b, direction):
    if a is None or b is None or a == 0:
        return "NA"
    pct = (b - a) / abs(a) * 100.0
    improvement = -pct if direction == "lower" else pct
    sign = "+" if improvement >= 0 else ""
    return f"{sign}{improvement:.1f}%"

def winner(a, b, direction):
    if a is None or b is None:
        return "NA"
    tol = max(abs(a), abs(b), 1.0) * 0.005
    if abs(a - b) <= tol:
        return "Tie"
    if direction == "lower":
        return "Spark" if a < b else "Qwen"
    return "Spark" if a > b else "Qwen"

concurrency_values = [int(x) for x in concs.split() if x.strip()]

with open(dst, "w", encoding="utf-8") as f:
    f.write("# Spark-X2.5-4B vs Qwen3-4B — Model Benchmark + Diagnostics\n\n")
    f.write(f"- Run ID: `{run_id}`\n")
    f.write(f"- Host: `{host_desc}`\n")
    f.write(f"- GPU: `{gpu_desc}`\n")
    f.write(f"- AIPerf profiling requests per cell: **{requests}**; warmup: **{warmup}**; repeats: **{repeats}**\n")
    f.write(f"- Concurrency: **{concs}**; output cap: **{osl} tokens**\n")
    f.write("- Engine fixed: **llama.cpp**\n")
    f.write("- Quantization fixed: **Q4_K_M**\n")
    f.write("- Workload fixed: identical raw-text prompts, identical order, `temperature=0`, `ignore_eos=true`\n")
    f.write("- Independent variable: **model** (checkpoint/architecture/tokenizer treated as the model package)\n")
    f.write(f"- Spark GGUF SHA256: `{spark_sha or 'unknown'}`\n")
    f.write(f"- Qwen GGUF SHA256: `{qwen_sha or 'unknown'}`\n\n")

    f.write("## Run validity\n\n")
    f.write("| Concurrency | Spark PASS / total | Qwen PASS / total | Spark mean error | Qwen mean error |\n")
    f.write("|---:|---:|---:|---:|---:|\n")
    for c in concurrency_values:
        sr = [r for r in rows if r["arm"] == "spark_llama" and r["concurrency"] == str(c)]
        qr = [r for r in rows if r["arm"] == "qwen_llama" and r["concurrency"] == str(c)]
        sp = sum(r["status"] == "PASS" for r in sr)
        qp = sum(r["status"] == "PASS" for r in qr)
        se = [float(r["error_rate_pct"]) for r in sr if r.get("error_rate_pct", "") not in ("", "NA")]
        qe = [float(r["error_rate_pct"]) for r in qr if r.get("error_rate_pct", "") not in ("", "NA")]
        sem = statistics.mean(se) if se else float("nan")
        qem = statistics.mean(qe) if qe else float("nan")
        f.write(f"| {c} | {sp}/{len(sr)} | {qp}/{len(qr)} | {sem:.2f}% | {qem:.2f}% |\n")

    f.write("\n## Side-by-side results\n\n")
    f.write("Values are mean ± 95% CI across successfully parsed repeats (PASS + UNSTABLE). `Δ Qwen vs Spark` is positive when Qwen is better for that metric.\n\n")
    for c in concurrency_values:
        f.write(f"### Concurrency {c}\n\n")
        f.write("| Metric | Spark | Qwen | Δ Qwen vs Spark | Winner |\n")
        f.write("|---|---:|---:|---:|---|\n")
        for key, label, unit, direction, primary in metrics:
            sa, sci, _ = stats("spark_llama", c, key)
            qa, qci, _ = stats("qwen_llama", c, key)
            f.write(f"| {label} | {fmt(sa, sci, unit)} | {fmt(qa, qci, unit)} | {delta(sa, qa, direction)} | {winner(sa, qa, direction)} |\n")
        f.write("\n")

    f.write("## Primary-metric win summary\n\n")
    f.write("Primary metrics are reliability, TTFT, ITL, E2E latency, and request throughput. Resource usage is reported separately rather than folded into a synthetic score.\n\n")
    f.write("| Concurrency | Spark wins | Qwen wins | Ties / NA |\n")
    f.write("|---:|---:|---:|---:|\n")
    for c in concurrency_values:
        sw = qw = ti = 0
        for key, label, unit, direction, primary in metrics:
            if not primary:
                continue
            sa, _, _ = stats("spark_llama", c, key)
            qa, _, _ = stats("qwen_llama", c, key)
            w = winner(sa, qa, direction)
            if w == "Spark": sw += 1
            elif w == "Qwen": qw += 1
            else: ti += 1
        f.write(f"| {c} | {sw} | {qw} | {ti} |\n")

    f.write("\n## Interpretation notes\n\n")
    f.write("- Treat **error rate as a hard gate**. A faster arm with materially higher request failures is not the better serving result.\n")
    f.write("- For interactive use, prioritize **TTFT p95** and **E2E p95**. For saturation behavior, prioritize **request throughput** together with error rate.\n")
    f.write("- `Output throughput*` is secondary across different models because their tokenizers differ; request-level latency/throughput is more directly comparable under identical raw prompts.\n")
    f.write("- Peak VRAM and power are efficiency metrics, not quality metrics; do not merge them into latency/throughput without an explicit weighting policy.\n")
PY

# Append scaling/error diagnostics to the SAME model_comparison.md.
python3 - "$ROWS" "$ERRORS" "$REPORT" <<'PY'
import csv, collections, statistics, sys
rowsf, errf, report = sys.argv[1:]
rows = list(csv.DictReader(open(rowsf, encoding="utf-8"), delimiter="\t"))
rows = [r for r in rows if r["suite"] == "model" and r["status"] in ("PASS", "UNSTABLE")]
errs = list(csv.DictReader(open(errf, encoding="utf-8"), delimiter="\t"))

arms = [("spark_llama", "Spark"), ("qwen_llama", "Qwen")]

def vals(arm, c, key):
    out = []
    for r in rows:
        if r["arm"] == arm and r["concurrency"] == str(c) and r.get(key, "") not in ("", "NA"):
            try:
                out.append(float(r[key]))
            except Exception:
                pass
    return out

cs = sorted({int(r["concurrency"]) for r in rows if r["concurrency"].isdigit()})

with open(report, "a", encoding="utf-8") as f:
    f.write("\n## Diagnostic findings\n\n")
    f.write("### Scaling curve\n\n")
    f.write("| Model | C | req/s mean | scaling vs C1 | efficiency vs ideal |\n")
    f.write("|---|---:|---:|---:|---:|\n")
    for arm, label in arms:
        base = statistics.mean(vals(arm, 1, "request_tps")) if vals(arm, 1, "request_tps") else None
        for c in cs:
            xs = vals(arm, c, "request_tps")
            if not xs:
                continue
            m = statistics.mean(xs)
            scaling = (m / base) if base else 0
            eff = (scaling / c) if c else 0
            f.write(f"| {label} | {c} | {m:.3f} | {scaling:.2f}x | {eff*100:.1f}% |\n")

    f.write("\n### Automatic anomaly flags\n\n")
    flags = []
    for arm, label in arms:
        means = {}
        for c in cs:
            xs = vals(arm, c, "request_tps")
            if xs:
                means[c] = statistics.mean(xs)
        prev = None
        for c in sorted(means):
            if prev is not None and means[c] < means[prev] * 0.90:
                flags.append(f"- **{label}: throughput regression** C={prev} → C={c}: {means[prev]:.3f} → {means[c]:.3f} req/s.")
            prev = c
        for c in cs:
            e = vals(arm, c, "error_rate_pct")
            if e and statistics.mean(e) > 1.0:
                flags.append(f"- **{label}: reliability issue** C={c}: mean error rate {statistics.mean(e):.2f}%.")
    if flags:
        f.write("\n".join(flags) + "\n")
    else:
        f.write("- No automatic scaling/reliability anomaly detected.\n")

    f.write("\n### Error-type breakdown\n\n")
    f.write("| Model | C | Error type | Count |\n")
    f.write("|---|---:|---|---:|\n")
    ctr = collections.Counter()
    for e in errs:
        if e["suite"] != "model":
            continue
        label = "Spark" if e["arm"] == "spark_llama" else "Qwen"
        ctr[(label, e["concurrency"], e["error_type"])] += int(e["count"])
    if ctr:
        for (label, c, t), n in sorted(ctr.items()):
            f.write(f"| {label} | {c} | `{t}` | {n} |\n")
    else:
        f.write("| - | - | No exported request errors | 0 |\n")

    f.write("\n### What this run is testing\n\n")
    f.write("- `cache_prompt=false` is sent on every request to remove prompt-cache reuse as a confounder.\n")
    f.write("- C=3 is added specifically to test whether the previous Qwen C=2 throughput collapse is a real scheduling/batching discontinuity or a one-point anomaly.\n")
    f.write("- Per-cell `server.log`, `props.json`, `container.txt`, `gpu.csv`, AIPerf records, and classified request errors are retained for root-cause analysis.\n")
    f.write("- Cross-model `tokens/s` remains secondary because Spark and Qwen tokenize the identical raw text differently.\n")
PY

log "===== complete ====="
log "raw=$ROWS"
log "aggregate=$OUT/aggregate.tsv"
log "MODEL REPORT=$REPORT"
log "ERROR DETAILS=$ERRORS"
log "RUNTIME CONFIG=$CONFIG_REPORT"
log "summary=$SUMMARY"
