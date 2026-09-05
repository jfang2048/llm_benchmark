#!/usr/bin/env bash
# Build the serving images used by the benchmark.
#   spark-x25-llama:cuda13  (llama.cpp w/ Spark architecture support, CUDA 13)
#   vllm-openai-gguf:v0.26.0 (vLLM 0.26.0 + vllm-gguf-plugin)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$ROOT/benchmark/config.env" ]] && set -a && . "$ROOT/benchmark/config.env" && set +a || true

LLAMA_IMAGE="${LLAMA_IMAGE:-spark-x25-llama:cuda13}"
VLLM_BASE_IMAGE="${VLLM_BASE_IMAGE:-vllm/vllm-openai:v0.26.0}"
VLLM_GGUF_IMAGE="${VLLM_GGUF_IMAGE:-vllm-openai-gguf:v0.26.0}"
VLLM_GGUF_PLUGIN_VERSION="${VLLM_GGUF_PLUGIN_VERSION:-0.0.4}"

need(){ command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing $1" >&2; exit 1; }; }
need docker

echo "== Building llama.cpp image: $LLAMA_IMAGE =="
if docker image inspect "$LLAMA_IMAGE" >/dev/null 2>&1; then
  echo "Image already exists: $LLAMA_IMAGE (skipping; delete to rebuild)"
else
  docker build -f "$ROOT/docker/llama-cpp/Dockerfile" -t "$LLAMA_IMAGE" "$ROOT/docker/llama-cpp"
fi

echo "== Building vLLM GGUF image: $VLLM_GGUF_IMAGE =="
if docker image inspect "$VLLM_GGUF_IMAGE" >/dev/null 2>&1; then
  echo "Image already exists: $VLLM_GGUF_IMAGE (skipping; delete to rebuild)"
else
  # Build context is the repo root; the Dockerfile derives from the vLLM base.
  docker build -f "$ROOT/docker/vllm-gguf/Dockerfile" -t "$VLLM_GGUF_IMAGE" "$ROOT"
fi

# Record provenance (image digests) for reproducibility.
{
  echo "prepared_at=$(date -Iseconds)"
  echo "llama_image=$LLAMA_IMAGE"
  echo "vllm_base_image=$VLLM_BASE_IMAGE"
  echo "vllm_gguf_image=$VLLM_GGUF_IMAGE"
  echo "vllm_gguf_plugin=$VLLM_GGUF_PLUGIN_VERSION"
  docker image inspect "$LLAMA_IMAGE" --format 'llama_image_id={{.Id}}'
  docker image inspect "$VLLM_BASE_IMAGE" --format 'vllm_image_id={{.Id}}' 2>/dev/null || echo "vllm_image_id=(pulled at deploy time)"
  docker image inspect "$VLLM_GGUF_IMAGE" --format 'vllm_gguf_image_id={{.Id}}'
} > "$ROOT/benchmark/cross_bench_provenance.txt"

echo
echo "Build complete. Image digests recorded in benchmark/cross_bench_provenance.txt"
