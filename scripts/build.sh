#!/usr/bin/env bash
# Build the serving images required by the current benchmark.
#
# Two engine profiles (see configs/models.json -> engines):
#   upstream_llama_cpp -> llama-cpp-upstream:v0.4.0  (docker/llama-cpp-upstream/)
#   xhtoken_llama_cpp  -> spark-x25-llama:cuda13     (docker/llama-cpp/)
#
# The vLLM image is secondary/backend work and is skipped unless
# BUILD_VLLM=1 is set. Existing images are reused unless FORCE=1.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

need(){ command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing $1" >&2; exit 1; }; }
need docker

# engine name -> (image, dockerfile context dir) from the registry
declare -A ENGINE_IMAGE ENGINE_DIR
while IFS=$'\t' read -r name image dir; do
  ENGINE_IMAGE["$name"]="$image"
  ENGINE_DIR["$name"]="$dir"
done < <(python3 - "$ROOT" <<'PY'
import json, sys
d = json.load(open(f"{sys.argv[1]}/configs/models.json"))
DIR = {
    "upstream_llama_cpp": "docker/llama-cpp-upstream",
    "xhtoken_llama_cpp": "docker/llama-cpp",
}
for name, e in d.get("engines", {}).items():
    print(f"{name}\t{e.get('image','')}\t{DIR.get(name,'')}")
PY
)

build_image(){
  local name="$1" image="$2" dir="$3"
  [[ -n "$image" && -n "$dir" ]] || { echo "SKIP engine $name (no image/dir)" >&2; return 0; }
  if [[ "${FORCE:-0}" != "1" ]] && docker image inspect "$image" >/dev/null 2>&1; then
    echo "Image already exists: $image (skip; FORCE=1 to rebuild)"
    return 0
  fi
  echo "== Building $name -> $image (context $dir) =="
  docker build -f "$ROOT/$dir/Dockerfile" -t "$image" "$ROOT/$dir"
}

for name in upstream_llama_cpp xhtoken_llama_cpp; do
  build_image "$name" "${ENGINE_IMAGE[$name]:-}" "${ENGINE_DIR[$name]:-}"
done

if [[ "${BUILD_VLLM:-0}" == "1" ]]; then
  VLLM_IMAGE="${VLLM_GGUF_IMAGE:-vllm-openai-gguf:v0.26.0}"
  if docker image inspect "$VLLM_IMAGE" >/dev/null 2>&1; then
    echo "vLLM image already exists: $VLLM_IMAGE (skip)"
  else
    echo "== Building vLLM GGUF image: $VLLM_IMAGE =="
    docker build -f "$ROOT/docker/vllm-gguf/Dockerfile" -t "$VLLM_IMAGE" "$ROOT"
  fi
fi

echo
echo "Build complete. Image IDs:"
for name in upstream_llama_cpp xhtoken_llama_cpp; do
  img="${ENGINE_IMAGE[$name]:-}"
  [[ -n "$img" ]] && docker image inspect "$img" --format "  $name {{.ID}}"
done
