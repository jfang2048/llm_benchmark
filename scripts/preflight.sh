#!/usr/bin/env bash
# Preflight: validate the machine before building/deploying/benchmarking.
# Produces [PASS]/[WARN]/[FAIL] lines and exits non-zero on any FAIL.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${MODEL_DIR:-$ROOT/models}"
PASS=0; WARN=0; FAIL=0

ok(){   printf '[PASS] %s\n' "$*"; PASS=$((PASS+1)); }
warn(){ printf '[WARN] %s\n' "$*"; WARN=$((WARN+1)); }
fail(){ printf '[FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }

have(){ command -v "$1" >/dev/null 2>&1; }

echo "== Operating system =="
if grep -qi microsoft /proc/version 2>/dev/null; then
  ok "WSL2 detected ($(uname -r))"
elif [[ "$(uname -s)" == "Linux" ]]; then
  ok "Linux detected ($(uname -r))"
else
  fail "This benchmark requires Linux (native or WSL2), got: $(uname -s)"
fi

echo "== Core tools =="
for c in curl python3 sha256sum; do
  have "$c" && ok "$c: $(command -v "$c")" || fail "missing command: $c"
done

echo "== Docker =="
if ! have docker; then
  fail "docker not installed"
else
  ok "docker client: $(docker version --format '{{.Client.Version}}' 2>/dev/null || echo '?')"
  if docker info >/dev/null 2>&1; then
    ok "docker daemon reachable"
    ok "docker server: $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?')"
  else
    fail "docker daemon not reachable — start Docker (Docker Desktop / dockerd) first"
  fi
fi
have docker-compose && ok "docker-compose available" || true
if docker compose version >/dev/null 2>&1; then
  ok "docker compose: $(docker compose version 2>/dev/null | awk '{print $NF}')"
else
  warn "docker compose plugin not found (only needed for the observability stack)"
fi

echo "== NVIDIA GPU =="
if ! have nvidia-smi; then
  fail "nvidia-smi not found — install NVIDIA driver + container toolkit"
else
  gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1)"
  vram="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -n1)"
  driver="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n1)"
  if [[ -n "$gpu_name" ]]; then
    ok "GPU: $gpu_name"
    ok "VRAM: ${vram} MiB"
    ok "driver: $driver"
  else
    fail "nvidia-smi ran but returned no GPU"
  fi
  if [[ -n "${vram:-}" ]] && (( vram < 6144 )); then
    warn "VRAM < 6 GiB; the 4B-class Q4_K_M matrix may not fit — expect OOM"
  fi
fi

echo "== Docker GPU passthrough =="
if have docker && docker info >/dev/null 2>&1 && have nvidia-smi; then
  if docker run --rm --gpus all nvidia/cuda:13.3.1-base-ubuntu24.04 nvidia-smi -L >/dev/null 2>&1; then
    ok "docker --gpus all works"
  else
    warn "docker GPU passthrough failed — install/enable the NVIDIA Container Toolkit"
  fi
else
  warn "skipped GPU passthrough check (docker or nvidia-smi unavailable)"
fi

echo "== Disk space =="
if have df; then
  avail_kb="$(df -Pk "$ROOT" 2>/dev/null | awk 'NR==2{print $4}')"
  if [[ -n "${avail_kb:-}" ]]; then
    avail_gb=$(( avail_kb / 1024 / 1024 ))
    ok "disk free: ${avail_gb} GiB"
    if (( avail_gb < 20 )); then
      warn "less than 20 GiB free — two 4B GGUFs (~4.9 GiB) plus images (~10+ GiB) need space"
    fi
  fi
fi

echo "== Model files =="
QWEN_GGUF="${QWEN_GGUF_FILE:-Qwen3-4B-Q4_K_M.gguf}"
SPARK_GGUF="${SPARK_GGUF_FILE:-Spark-X2.5-4B-Q4_K_M.gguf}"
if [[ -s "$MODEL_DIR/$QWEN_GGUF" ]]; then
  ok "Qwen GGUF present: $MODEL_DIR/$QWEN_GGUF"
else
  warn "Qwen GGUF missing — run: make setup (scripts/download_models.sh)"
fi
if [[ -s "$MODEL_DIR/$SPARK_GGUF" ]]; then
  ok "Spark GGUF present: $MODEL_DIR/$SPARK_GGUF"
else
  warn "Spark GGUF missing — see models/README.md for acquisition steps"
fi

echo "== Benchmark ports (8100-8103) =="
for p in 8100 8101 8102 8103; do
  if have ss && ss -ltn 2>/dev/null | grep -q ":$p "; then
    warn "port $p already in use"
  elif have curl && curl -s --max-time 2 "http://127.0.0.1:$p/health" >/dev/null 2>&1; then
    warn "port $p already in use (an HTTP service responded)"
  else
    ok "port $p available"
  fi
done

echo
echo "== Summary: $PASS pass, $WARN warn, $FAIL fail =="
if (( FAIL > 0 )); then
  echo "Fix the FAIL items above before continuing."
  exit 1
fi
if (( WARN > 0 )); then
  echo "WARN items are non-fatal but should be reviewed."
fi
exit 0
