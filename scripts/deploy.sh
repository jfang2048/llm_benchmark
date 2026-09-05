#!/usr/bin/env bash
# Create the four benchmark serving containers (stopped, ready to start).
# Mirrors the validated experiment: two llama.cpp arms (the primary model
# comparison) and two vLLM arms (the engine-comparison context).
#
# Ports are isolated from the everyday 8000/8001 deployments:
#   bench-spark-llama      127.0.0.1:8100  (llama.cpp)
#   bench-qwen-llama       127.0.0.1:8101  (llama.cpp)
#   bench-qwen-vllm-gguf   127.0.0.1:8102  (vLLM + GGUF plugin)
#   bench-qwen-vllm-awq    127.0.0.1:8103  (vLLM + AWQ)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${MODEL_DIR:-$ROOT/models}"
HF_CACHE="${HF_CACHE:-$ROOT/.cache/huggingface}"
VLLM_CACHE="${VLLM_CACHE:-$ROOT/.cache/vllm}"
mkdir -p "$HF_CACHE" "$VLLM_CACHE"
[[ -f "$ROOT/benchmark/config.env" ]] && set -a && . "$ROOT/benchmark/config.env" && set +a || true

LLAMA_IMAGE="${LLAMA_IMAGE:-spark-x25-llama:cuda13}"
VLLM_BASE_IMAGE="${VLLM_BASE_IMAGE:-vllm/vllm-openai:v0.26.0}"
VLLM_GGUF_IMAGE="${VLLM_GGUF_IMAGE:-vllm-openai-gguf:v0.26.0}"
QWEN_GGUF="${QWEN_GGUF_FILE:-Qwen3-4B-Q4_K_M.gguf}"
SPARK_GGUF="${SPARK_GGUF_FILE:-Spark-X2.5-4B-Q4_K_M.gguf}"

PER_REQUEST_CTX="${PER_REQUEST_CTX:-2304}"
MAX_CONCURRENCY="${MAX_CONCURRENCY:-4}"
LLAMA_TOTAL_CTX=$(( PER_REQUEST_CTX * MAX_CONCURRENCY ))
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.80}"

need(){ command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing $1" >&2; exit 1; }; }
need docker

[[ -s "$MODEL_DIR/$QWEN_GGUF" ]] || { echo "ERROR: $MODEL_DIR/$QWEN_GGUF missing — run scripts/download_models.sh" >&2; exit 2; }
[[ -s "$MODEL_DIR/$SPARK_GGUF" ]] || { echo "ERROR: $MODEL_DIR/$SPARK_GGUF missing — see models/README.md" >&2; exit 2; }

# Remove any previous instances so `docker create` cannot fail on name clash.
for c in bench-spark-llama bench-qwen-llama bench-qwen-vllm-gguf bench-qwen-vllm-awq; do
  docker rm -f "$c" >/dev/null 2>&1 || true
done

# llama.cpp: --ctx-size is the TOTAL context shared by --parallel slots.
common_llama=(
  --host 0.0.0.0 --port 8000
  --ctx-size "$LLAMA_TOTAL_CTX"
  --parallel "$MAX_CONCURRENCY"
  --cont-batching --metrics
  --n-gpu-layers 999
)

docker create \
  --name bench-spark-llama \
  --gpus all --ipc host \
  -p 127.0.0.1:8100:8000 \
  -v "$MODEL_DIR:/bench-models:ro" \
  --entrypoint /src/build/bin/llama-server \
  "$LLAMA_IMAGE" \
  --model "/bench-models/$SPARK_GGUF" \
  --alias Spark-X2.5-4B-Q4_K_M \
  "${common_llama[@]}" >/dev/null

docker create \
  --name bench-qwen-llama \
  --gpus all --ipc host \
  -p 127.0.0.1:8101:8000 \
  -v "$MODEL_DIR:/bench-models:ro" \
  --entrypoint /src/build/bin/llama-server \
  "$LLAMA_IMAGE" \
  --model "/bench-models/$QWEN_GGUF" \
  --alias Qwen3-4B-Q4_K_M \
  "${common_llama[@]}" >/dev/null

common_vllm=(
  --max-model-len "$PER_REQUEST_CTX"
  --gpu-memory-utilization "$GPU_MEM_UTIL"
  --max-num-seqs "$MAX_CONCURRENCY"
  --generation-config vllm
  --reasoning-parser qwen3
  --default-chat-template-kwargs '{"enable_thinking": false}'
)

docker create \
  --name bench-qwen-vllm-gguf \
  --gpus all --ipc host \
  -e VLLM_WSL2_ENABLE_PIN_MEMORY=1 \
  -p 127.0.0.1:8102:8000 \
  -v "$MODEL_DIR:/bench-models:ro" \
  -v "$HF_CACHE:/root/.cache/huggingface" \
  "$VLLM_GGUF_IMAGE" \
  "/bench-models/$QWEN_GGUF" \
  --served-model-name Qwen3-4B-Q4_K_M \
  --tokenizer Qwen/Qwen3-4B \
  "${common_vllm[@]}" >/dev/null

docker create \
  --name bench-qwen-vllm-awq \
  --gpus all --ipc host \
  -e VLLM_WSL2_ENABLE_PIN_MEMORY=1 \
  -p 127.0.0.1:8103:8000 \
  -v "$HF_CACHE:/root/.cache/huggingface" \
  "$VLLM_BASE_IMAGE" \
  Qwen/Qwen3-4B-AWQ \
  --served-model-name Qwen3-4B-AWQ \
  "${common_vllm[@]}" >/dev/null

echo "Created benchmark containers (all stopped):"
for c in bench-spark-llama bench-qwen-llama bench-qwen-vllm-gguf bench-qwen-vllm-awq; do
  printf '  %-22s -> %s\n' "$c" "$(docker inspect -f '{{json .Config.Cmd}}' "$c" 2>/dev/null | head -c 110)"
done
echo
echo "Next: ./scripts/healthcheck.sh   (prove every arm starts)"
echo "      ./scripts/benchmark.sh smoke | final"
