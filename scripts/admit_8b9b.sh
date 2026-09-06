#!/usr/bin/env bash
# Admission test for the mainstream 8-9B cohort on the pinned upstream
# llama.cpp image. For each model: serve -> healthcheck -> 1 generation ->
# 20-request smoke -> VRAM/OOM check -> stop. One container at a time.
#
# Usage: ./scripts/admit_8b9b.sh [model_id ...]   (default: all 4)
# Env:   CTX_SIZE=4096 PARALLEL=2 IMAGE=llama-cpp-upstream:v0.4.0
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${MODEL_DIR:-$ROOT/models}"
IMAGE="${IMAGE:-llama-cpp-upstream:v0.4.0}"
CTX_SIZE="${CTX_SIZE:-4096}"
PARALLEL="${PARALLEL:-2}"
N_GPU_LAYERS="${N_GPU_LAYERS:-999}"
SMOKE_REQS="${SMOKE_REQS:-20}"
OUT_LEN="${OUT_LEN:-128}"

# id | gguf file | port | display name
MODELS=(
  "qwen3_8b|Qwen3-8B-IQ4_XS.gguf|8200|Qwen3-8B-IQ4_XS"
  "deepseek_r1_8b|DeepSeek-R1-Distill-Llama-8B-IQ4_XS.gguf|8201|DeepSeek-R1-Distill-Llama-8B-IQ4_XS"
  "glm4_9b|GLM-4-9B-0414-IQ4_XS.gguf|8202|GLM-4-9B-0414-IQ4_XS"
  "yi_15_9b|Yi-1.5-9B-Chat-IQ4_XS.gguf|8203|Yi-1.5-9B-Chat-IQ4_XS"
)

SELECT="${*:-}"

need(){ command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing $1" >&2; exit 1; }; }
need docker; need curl; need nvidia-smi

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
  if docker logs "$c" 2>&1 | grep -qiE "out of memory|CUDA error|OOM|failed to allocate"; then
    echo "OOM-SUSPECT"
  else
    echo "no-oom"
  fi
}

summary_file="$ROOT/.agent/admission.tsv"
printf 'model\tport\tctx\tparallel\tn_gpu_layers\tvram_used_mib\tvram_total_mib\tgen_tokens\tsmoke\tstatus\n' > "$summary_file"

for entry in "${MODELS[@]}"; do
  IFS='|' read -r id gguf port name <<< "$entry"
  [[ -n "$SELECT" && " $SELECT " != *" $id "* ]] && continue
  gguf_path="$MODEL_DIR/$gguf"
  [[ -s "$gguf_path" ]] || { echo "[$id] SKIP: $gguf_path missing"; echo -e "$id\t$port\t$CTX_SIZE\t$PARALLEL\t$N_GPU_LAYERS\t-\t-\t-\tmissing-gguf\tSKIP" >> "$summary_file"; continue; }

  c="admit-${id//_/-}"
  docker rm -f "$c" >/dev/null 2>&1 || true
  echo "=== [$id] serving $gguf (ctx=$CTX_SIZE parallel=$PARALLEL ngpu=$N_GPU_LAYERS) ==="
  docker run -d --name "$c" --gpus all --ipc host \
    -p "127.0.0.1:${port}:8000" \
    -v "$MODEL_DIR:/models:ro" \
    --entrypoint /src/build/bin/llama-server \
    "$IMAGE" \
    --model "/models/$gguf" --alias "$name" \
    --host 0.0.0.0 --port 8000 \
    --ctx-size "$CTX_SIZE" --parallel "$PARALLEL" \
    --cont-batching --metrics --n-gpu-layers "$N_GPU_LAYERS" >/dev/null

  if ! wait_ready "$c" "$port"; then
    echo "[$id] FAIL: did not become ready"
    docker logs --tail 30 "$c" >&2 2>/dev/null || true
    echo -e "$id\t$port\t$CTX_SIZE\t$PARALLEL\t$N_GPU_LAYERS\t-\t-\t-\t-\tFAIL-START" >> "$summary_file"
    docker rm -f "$c" >/dev/null 2>&1 || true
    continue
  fi

  vr="$(vram)"
  used="${vr%%,*}"; total="${vr##*,}"
  echo "[$id] ready; VRAM ${used}/${total} MiB"

  body="$(gen_once "$port" "$name")"
  toks="$(echo "$body" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["usage"]["completion_tokens"] if "usage" in d else "?")' 2>/dev/null)"
  echo "[$id] gen tokens=$toks"

  sm="$(smoke "$port" "$name")"
  echo "[$id] $sm"

  oo="$(oom_check "$c")"
  echo "[$id] oom=$oo"

  docker stop "$c" >/dev/null 2>&1 || true
  docker rm -f "$c" >/dev/null 2>&1 || true

  echo -e "$id\t$port\t$CTX_SIZE\t$PARALLEL\t$N_GPU_LAYERS\t$used\t$total\t$toks\t$sm\t$oo" >> "$summary_file"
done

echo "=== ADMISSION SUMMARY ==="
cat "$summary_file"
