#!/usr/bin/env bash
# Admission test for the current benchmark models (registry-driven).
#
# For each selected model: serve with the cohort engine -> healthcheck ->
# /v1/models -> one generation -> 20-request smoke -> VRAM/OOM check -> stop.
# One container at a time. The engine image is derived from the cohort via
# configs/models.json (engines{} + cohorts{}), not a hardcoded table.
#
# Usage: ./scripts/admit.sh [model_id ...]   (default: all current models)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${MODEL_DIR:-$ROOT/models}"
CTX_SIZE="${CTX_SIZE:-4096}"
PARALLEL="${PARALLEL:-2}"
N_GPU_LAYERS="${N_GPU_LAYERS:-999}"
SMOKE_REQS="${SMOKE_REQS:-20}"
OUT_LEN="${OUT_LEN:-128}"

need(){ command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing $1" >&2; exit 1; }; }
need docker; need curl; need nvidia-smi; need python3

# id<TAB>gguf<TAB>port<TAB>alias<TAB>image   (image resolved from cohort -> engine)
MODELS="$(python3 - "$ROOT" "$@" <<'PYTHON'
import sys
sys.path.insert(0, sys.argv[1])
from bench.config import admission_models, cohort_engine, engine_image

for m in admission_models(sys.argv[2:]):
    image = engine_image(cohort_engine(m["cohort"]))
    if not image:
        sys.exit(f"No engine image for {m['id']}")
    print("\t".join([m["id"], m["gguf_filename"], str(m["port"]), m["arm"], image]))
PYTHON
)" || exit 1

vram(){ nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null | head -n1 | tr -d ' '; }

wait_ready(){
  local c="$1" port="$2" start now
  start=$(date +%s)
  while :; do
    [[ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null || true)" == true ]] || return 1
    if curl -fsS --max-time 2 "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then return 0; fi
    now=$(date +%s); (( now - start >= 300 )) && return 1
    sleep 2
  done
}

gen_once(){
  local port="$1" name="$2"
  curl -fsS --max-time 180 "http://127.0.0.1:${port}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "{\"model\":\"$name\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hello in one sentence.\"}],\"max_tokens\":$OUT_LEN,\"temperature\":0}" 2>/dev/null
}

smoke(){
  local port="$1" name="$2" i ok=0 fail=0
  for ((i=1; i<=SMOKE_REQS; i++)); do
    if curl -fsS --max-time 180 "http://127.0.0.1:${port}/v1/chat/completions" \
       -H 'Content-Type: application/json' \
       -d "{\"model\":\"$name\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello.\"}],\"max_tokens\":$OUT_LEN,\"temperature\":0}" \
       >/dev/null 2>&1; then ok=$((ok+1)); else fail=$((fail+1)); fi
  done
  echo "smoke ok=$ok fail=$fail"
}

oom_check(){
  local c="$1"
  local logs
  if ! logs="$(docker logs "$c" 2>&1)"; then
    echo "FAIL-LOGS"
  elif grep -qiE 'out of memory|CUDA error|failed to allocate|\bOOM\b' <<< "$logs"; then
    echo "OOM-SUSPECT"
  else
    echo "no-oom"
  fi
}

summary_file="$ROOT/.agent/admission.tsv"
mkdir -p "$(dirname "$summary_file")" || exit 1
printf 'model\timage\tport\tctx\tparallel\tn_gpu_layers\tvram_used_mib\tvram_total_mib\tgen_tokens\tsmoke\tstatus\n' > "$summary_file" || exit 1
failed=0

while IFS=$'\t' read -r id gguf port alias image; do
  [[ -n "$id" ]] || continue
  gguf_path="$MODEL_DIR/$gguf"
  if [[ ! -s "$gguf_path" ]]; then
    echo "[$id] FAIL: $gguf_path missing"
    printf '%s\t%s\t%s\t%s\t%s\t%s\t-\t-\t-\t-\tFAIL-MISSING\n' \
      "$id" "$image" "$port" "$CTX_SIZE" "$PARALLEL" "$N_GPU_LAYERS" >> "$summary_file"
    failed=1
    continue
  fi

  c="admit-${id//_/-}"
  docker rm -f "$c" >/dev/null 2>&1 || true
  echo "=== [$id] serving $gguf (image=$image ctx=$CTX_SIZE parallel=$PARALLEL) ==="
  if ! docker run -d --name "$c" --gpus all --ipc host \
    -p "127.0.0.1:${port}:8000" \
    -v "$MODEL_DIR:/models:ro" \
    --entrypoint /src/build/bin/llama-server \
    "$image" \
    --model "/models/$gguf" --alias "$alias" \
    --host 0.0.0.0 --port 8000 \
    --ctx-size "$CTX_SIZE" --parallel "$PARALLEL" \
    --cont-batching --metrics --n-gpu-layers "$N_GPU_LAYERS" >/dev/null ||
      ! wait_ready "$c" "$port"; then
    echo "[$id] FAIL: did not become ready"
    docker logs --tail 30 "$c" >&2 || true
    echo -e "$id\t$image\t$port\t$CTX_SIZE\t$PARALLEL\t$N_GPU_LAYERS\t-\t-\t-\t-\tFAIL-START" >> "$summary_file"
    docker rm -f "$c" >/dev/null 2>&1 || true
    failed=1
    continue
  fi

  vr="$(vram)"
  used="${vr%%,*}"; total="${vr##*,}"
  echo "[$id] ready; VRAM ${used}/${total} MiB"

  # Require the requested alias and a response with positive token usage.
  model_ok=0
  if curl -fsS --max-time 5 "http://127.0.0.1:$port/v1/models" |
      python3 -c 'import sys,json; sys.exit(not any(m["id"] == sys.argv[1] for m in json.load(sys.stdin)["data"]))' "$alias"; then
    model_ok=1
  fi
  echo "[$id] /v1/models alias present=$model_ok"

  toks="$(gen_once "$port" "$alias" | python3 -c 'import sys,json; print(json.load(sys.stdin)["usage"]["completion_tokens"])' 2>/dev/null)" || toks="-"
  echo "[$id] gen tokens=$toks"

  sm="$(smoke "$port" "$alias")"
  echo "[$id] $sm"

  oo="$(oom_check "$c")"
  echo "[$id] oom=$oo"

  docker stop "$c" >/dev/null 2>&1 || true
  docker rm -f "$c" >/dev/null 2>&1 || true

  status="$oo"
  if [[ "$status" == "no-oom" ]]; then
    if [[ "$model_ok" != 1 || ! "$toks" =~ ^[1-9][0-9]*$ ||
          "$sm" != "smoke ok=$SMOKE_REQS fail=0" ||
          ! "$vr" =~ ^[0-9]+,[0-9]+$ ]]; then
      status="FAIL-SMOKE"
    fi
  fi
  [[ "$status" == "no-oom" ]] || failed=1
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$id" "$image" "$port" "$CTX_SIZE" "$PARALLEL" "$N_GPU_LAYERS" \
    "$used" "$total" "$toks" "$sm" "$status" >> "$summary_file"
done <<< "$MODELS"

echo "=== ADMISSION SUMMARY ==="
cat "$summary_file"
exit "$failed"
