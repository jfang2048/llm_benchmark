#!/usr/bin/env bash
# Healthcheck: start each benchmark container once, prove it becomes API-ready,
# then stop it. This validates startup before an expensive benchmark run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$ROOT/benchmark/config.env" ]] && set -a && . "$ROOT/benchmark/config.env" && set +a || true
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-300}"

declare -A ARMS=(
  [bench-spark-llama]=8100
  [bench-qwen-llama]=8101
  [bench-qwen-vllm-gguf]=8102
  [bench-qwen-vllm-awq]=8103
)

need(){ command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing $1" >&2; exit 1; }; }
need docker; need curl

stop_all(){
  for c in "${!ARMS[@]}"; do
    docker inspect "$c" >/dev/null 2>&1 && docker stop "$c" >/dev/null 2>&1 || true
  done
}
trap stop_all EXIT

wait_ready(){
  local c="$1" port="$2" start now
  start=$(date +%s)
  while :; do
    [[ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null || true)" == true ]] || return 1
    if curl -fsS --max-time 2 "http://127.0.0.1:${port}/health" >/dev/null 2>&1 \
       && curl -fsS --max-time 2 "http://127.0.0.1:${port}/v1/models" >/dev/null 2>&1; then
      return 0
    fi
    now=$(date +%s)
    (( now - start >= STARTUP_TIMEOUT )) && return 1
    sleep 2
  done
}

stop_all
rc=0
for c in "${!ARMS[@]}"; do
  port="${ARMS[$c]}"
  if ! docker inspect "$c" >/dev/null 2>&1; then
    echo "[FAIL] $c: container missing — run scripts/deploy.sh"
    rc=1; continue
  fi
  printf 'Starting %s (127.0.0.1:%s) ... ' "$c" "$port"
  docker start "$c" >/dev/null
  if wait_ready "$c" "$port"; then
    model="$(curl -fsS "http://127.0.0.1:${port}/v1/models" 2>/dev/null | head -c 160)"
    echo "[PASS] $model"
  else
    echo "[FAIL] $c did not become API-ready"
    docker logs --tail 60 "$c" >&2 2>/dev/null || true
    rc=1
  fi
  docker stop "$c" >/dev/null 2>&1 || true
  sleep 2
done

echo
if (( rc == 0 )); then
  echo "All benchmark arms passed the startup healthcheck."
else
  echo "One or more arms failed; review logs above before benchmarking."
fi
exit $rc
