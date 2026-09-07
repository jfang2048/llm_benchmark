#!/usr/bin/env bash
# Preflight: validate the machine for the current benchmark.
# Emits [PASS]/[WARN]/[FAIL]; exits non-zero only on environment FAILs.
#
# Environment requirements are FAILs. Missing model files / engine images are
# WARNs (they are produced by `make setup`), so a fresh clone without models
# still passes environment preflight.
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
  fail "Requires Linux (native or WSL2), got: $(uname -s)"
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
  else
    fail "docker daemon not reachable - start Docker first"
  fi
fi

echo "== NVIDIA GPU =="
VRAM=""
if ! have nvidia-smi; then
  fail "nvidia-smi not found - install NVIDIA driver + container toolkit"
else
  gpu_name="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1)"
  VRAM="$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -n1)"
  driver="$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -n1)"
  if [[ -n "$gpu_name" ]]; then
    ok "GPU: $gpu_name"
    ok "VRAM: ${VRAM} MiB"
    ok "driver: $driver"
  else
    fail "nvidia-smi returned no GPU"
  fi
  if [[ -n "${VRAM:-}" ]] && (( VRAM < 6144 )); then
    warn "VRAM < 6 GiB; the 8-9B IQ4_XS cohort may not fit - expect OOM"
  fi
fi

echo "== Docker GPU passthrough =="
if have docker && docker info >/dev/null 2>&1 && have nvidia-smi; then
  if docker run --rm --gpus all nvidia/cuda:13.3.1-base-ubuntu24.04 nvidia-smi -L >/dev/null 2>&1; then
    ok "docker --gpus all works"
  else
    warn "docker GPU passthrough failed - install/enable the NVIDIA Container Toolkit"
  fi
fi

echo "== Python =="
if have python3; then
  ok "python3: $(python3 --version 2>&1)"
else
  fail "python3 not found"
fi

echo "== AIPerf =="
if have aiperf || [[ -x "$HOME/venvs/aiperf/bin/aiperf" ]]; then
  ok "AIPerf available"
else
  warn "AIPerf not found - install it (or set AIPERF=/path/to/aiperf) before benchmarking"
fi

echo "== Disk space =="
if have df; then
  avail_kb="$(df -Pk "$ROOT" 2>/dev/null | awk 'NR==2{print $4}')"
  if [[ -n "${avail_kb:-}" ]]; then
    avail_gb=$(( avail_kb / 1024 / 1024 ))
    ok "disk free: ${avail_gb} GiB"
    (( avail_gb < 25 )) && warn "less than 25 GiB free (4 IQ4_XS GGUFs ~18 GiB + images ~10+ GiB)"
  fi
fi

echo "== Current model files (registry) =="
while IFS=$'\t' read -r local sha; do
  [[ -n "$local" ]] || continue
  p="$MODEL_DIR/$local"
  if [[ -s "$p" ]]; then
    got="$(sha256sum "$p" | awk '{print $1}')"
    if [[ "$got" == "$sha" ]]; then
      ok "$local (verified)"
    else
      warn "$local present but SHA256 mismatch - re-download (make setup)"
    fi
  else
    warn "$local missing - run: make setup (scripts/download_models.sh)"
  fi
done < <(python3 - "$ROOT" <<'PY'
import json, sys
d = json.load(open(f"{sys.argv[1]}/configs/models.json"))
for m in d["models"]:
    if m.get("enabled") and m.get("cohort") in ("mainstream_8_9b", "spark_reference"):
        print(f"{m.get('gguf_filename','')}\t{m.get('sha256','')}")
PY
)

echo "== Engine images (registry) =="
while IFS=$'\t' read -r name image; do
  [[ -n "$image" ]] || continue
  if docker image inspect "$image" >/dev/null 2>&1; then
    ok "image $image present"
  else
    warn "image $image missing - run: make setup (scripts/build.sh)"
  fi
done < <(python3 - "$ROOT" <<'PY'
import json, sys
d = json.load(open(f"{sys.argv[1]}/configs/models.json"))
for name, e in d.get("engines", {}).items():
    print(f"{name}\t{e.get('image','')}")
PY
)

echo "== Benchmark ports =="
while IFS= read -r port; do
  [[ -n "$port" ]] || continue
  if have ss && ss -ltn 2>/dev/null | grep -q ":$port "; then
    warn "port $port already in use"
  elif have curl && curl -s --max-time 2 "http://127.0.0.1:$port/health" >/dev/null 2>&1; then
    warn "port $port already in use (HTTP service responded)"
  else
    ok "port $port available"
  fi
done < <(python3 - "$ROOT" <<'PY'
import json, sys
d = json.load(open(f"{sys.argv[1]}/configs/models.json"))
for m in d["models"]:
    if m.get("enabled") and m.get("cohort") in ("mainstream_8_9b", "spark_reference"):
        print(m.get("port", ""))
PY
)

echo
echo "== Summary: $PASS pass, $WARN warn, $FAIL fail =="
if (( FAIL > 0 )); then
  echo "Fix the FAIL items above before continuing."
  exit 1
fi
echo "WARN items are non-fatal; model files / images are produced by 'make setup'."
exit 0
