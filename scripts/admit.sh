#!/usr/bin/env bash
# Admission test for the current benchmark models (registry-driven).
#
# For each enabled model in the current cohorts (mainstream_8_9b and
# spark_reference): serve with the correct engine image -> healthcheck ->
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
SELECT="${*:-}"

need(){ command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing $1" >&2; exit 1; }; }
need docker; need curl; need nvidia-smi; need python3

# id<TAB>gguf<TAB>port<TAB>alias<TAB>image   (image resolved from cohort -> engine)
MODELS="$(python3 - "$ROOT" <<'PY'
import json, sys
d = json.load(open(f"{sys.argv[1]}/configs/models.json"))
img = {k: v.get("image", "") for k, v in d.get("engines", {}).items()}
eng = {k: v.get("engine", "") for k, v in d.get("cohorts", {}).items()}
for m in d["models"]:
    if not m.get("enabled"):
        continue
    if m.get("cohort") not in ("mainstream_8_9b", "spark_reference"):
        continue
    image = img.get(eng.get(m.get("cohort", ""), ""), "")
    print("\t".join([
        m.get("id", ""), m.get("gguf_filename", ""), str(m.get("port", "")),
        m.get("arm", ""), image,
    ]))
PY
)"

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
printf 'model\timage\tport\tctx\tparallel\tn_gpu_layers\tvram_used_mib\tvram_total_mib\tgen_tokens\tsmoke\tstatus\n' > "$summary_file"

while IFS=$'\t' read -r id gguf port alias image; do
  [[ -n "$id" ]] || continue
  [[ -z "$SELECT" || " $SELECT " == *" $id "* ]] || continue
  gguf_path="$MODEL_DIR/$gguf"
  [[ -s "$gguf_path" ]] || { echo "[$id] SKIP: $gguf_path missing"; echo -e "$id\t$image\t$port\t$CTX_SIZE\t$PARALLEL\t$N_GPU_LAYERS\t-\t-\t-\tmissing-gguf\tSKIP" >> "$summary_file"; continue; }
  [[ -n "$image" ]] || { echo "[$id] SKIP: no engine image resolved"; continue; }

  c="admit-${id//_/-}"
  docker rm -f "$c" >/dev/null 2>&1 || true
  echo "=== [$id] serving $gguf (image=$image ctx=$CTX_SIZE parallel=$PARALLEL) ==="
  docker run -d --name "$c" --gpus all --ipc host \
    -p "127.0.0.1:${port}:8000" \
    -v "$MODEL_DIR:/models:ro" \
    --entrypoint /src/build/bin/llama-server \
    "$image" \
    --model "/models/$gguf" --alias "$alias" \
    --host 0.0.0.0 --port 8000 \
    --ctx-size "$CTX_SIZE" --parallel "$PARALLEL" \
    --cont-batching --metrics --n-gpu-layers "$N_GPU_LAYERS" >/dev/null

  if ! wait_ready "$c" "$port"; then
    echo "[$id] FAIL: did not become ready"
    docker logs --tail 30 "$c" >&2 2>/dev/null || true
    echo -e "$id\t$image\t$port\t$CTX_SIZE\t$PARALLEL\t$N_GPU_LAYERS\t-\t-\t-\t-\tFAIL-START" >> "$summary_file"
    docker rm -f "$c" >/dev/null 2>&1 || true
    continue
  fi

  vr="$(vram)"
  used="${vr%%,*}"; total="${vr##*,}"
  echo "[$id] ready; VRAM ${used}/${total} MiB"

  # /v1/models sanity
  nmodels="$(curl -fsS --max-time 5 "http://127.0.0.1:${port}/v1/models" 2>/dev/null | python3 -c 'import sys,json; print(len(json.load(sys.stdin).get("data", [])))' 2>/dev/null || echo '?')"
  echo "[$id] /v1/models count=$nmodels"

  body="$(gen_once "$port" "$alias")"
  toks="$(echo "$body" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["usage"]["completion_tokens"] if "usage" in d else "?")' 2>/dev/null)"
  echo "[$id] gen tokens=$toks"

  sm="$(smoke "$port" "$alias")"
  echo "[$id] $sm"

  oo="$(oom_check "$c")"
  echo "[$id] oom=$oo"

  docker stop "$c" >/dev/null 2>&1 || true
  docker rm -f "$c" >/dev/null 2>&1 || true

  echo -e "$id\t$image\t$port\t$CTX_SIZE\t$PARALLEL\t$N_GPU_LAYERS\t$used\t$total\t$toks\t$sm\t$oo" >> "$summary_file"
done <<< "$MODELS"

echo "=== ADMISSION SUMMARY ==="
cat "$summary_file"
