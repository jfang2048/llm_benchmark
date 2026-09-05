#!/usr/bin/env bash
# Tear down benchmark containers and lock files. Does NOT delete model weights,
# caches, or results — only stops/removes the throwaway benchmark containers.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for c in bench-spark-llama bench-qwen-llama bench-qwen-vllm-gguf bench-qwen-vllm-awq; do
  if docker inspect "$c" >/dev/null 2>&1; then
    docker stop "$c" >/dev/null 2>&1 || true
    docker rm -f "$c" >/dev/null 2>&1 || true
    echo "removed container: $c"
  fi
done

rm -f "$ROOT/benchmark/.cross_benchmark.lock" "$ROOT/benchmark/.cross_benchmark.pid"
echo "cleanup complete (models, caches, and results left in place)"
