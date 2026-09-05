#!/usr/bin/env bash
# Download / verify model weights into models/ (never committed).
#
#   Qwen3-4B-Q4_K_M.gguf  — official Qwen GGUF repo (reliable public source)
#   Spark-X2.5-4B-Q4_K_M.gguf — must be provided by the user or converted from
#                                XHToken/Spark-X2.5-4B (see models/README.md)
#
# Every file is verified against a pinned SHA256. Existing valid files are skipped.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${MODEL_DIR:-$ROOT/models}"
mkdir -p "$MODEL_DIR"

# Source optional overrides (benchmark/config.env) without failing if absent.
[[ -f "$ROOT/benchmark/config.env" ]] && set -a && . "$ROOT/benchmark/config.env" && set +a || true

QWEN_REPO="${QWEN_GGUF_REPO:-Qwen/Qwen3-4B-GGUF}"
QWEN_FILE="${QWEN_GGUF_FILE:-Qwen3-4B-Q4_K_M.gguf}"
QWEN_URL="https://huggingface.co/${QWEN_REPO}/resolve/main/${QWEN_FILE}?download=true"
QWEN_SHA256="7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5"

SPARK_FILE="${SPARK_GGUF_FILE:-Spark-X2.5-4B-Q4_K_M.gguf}"
SPARK_SHA256="7934660bfc5b9bf04be0a0ac6179a1d16e1d4331b448857c86b8b2801b3ef72c"

need(){ command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing $1" >&2; exit 1; }; }
for c in curl sha256sum; do need "$c"; done

verify(){
  local file="$1" want="$2"
  if [[ ! -s "$file" ]]; then return 1; fi
  got="$(sha256sum "$file" | awk '{print $1}')"
  [[ "$got" == "$want" ]]
}

# --- Qwen3-4B GGUF -----------------------------------------------------------
QWEN_PATH="$MODEL_DIR/$QWEN_FILE"
if verify "$QWEN_PATH" "$QWEN_SHA256"; then
  echo "OK   $QWEN_FILE already present and verified"
else
  echo "Downloading $QWEN_FILE from $QWEN_REPO ..."
  curl -fL --retry 5 --retry-delay 3 -C - "$QWEN_URL" -o "$QWEN_PATH.part"
  mv "$QWEN_PATH.part" "$QWEN_PATH"
  if verify "$QWEN_PATH" "$QWEN_SHA256"; then
    echo "OK   $QWEN_FILE downloaded and SHA256 verified"
  else
    echo "ERROR: SHA256 mismatch for $QWEN_FILE — delete it and retry" >&2
    exit 1
  fi
fi

# --- Spark-X2.5-4B GGUF ------------------------------------------------------
SPARK_PATH="$MODEL_DIR/$SPARK_FILE"
if verify "$SPARK_PATH" "$SPARK_SHA256"; then
  echo "OK   $SPARK_FILE already present and verified"
else
  cat <<EOF >&2

--------------------------------------------------------------------------------
Spark-X2.5-4B-Q4_K_M.gguf is NOT auto-downloaded. There is no single canonical
public GGUF URL for the exact artifact used in this benchmark.

Expected file:  $SPARK_PATH
Expected SHA256: $SPARK_SHA256

Options:
  1. If you already have the file elsewhere, place it at the path above, e.g.:
       cp /path/to/Spark-X2.5-4B-Q4_K_M.gguf $SPARK_PATH
  2. Convert it from the official weights (XHToken/Spark-X2.5-4B) using the
     llama.cpp fork built in docker/llama-cpp/Dockerfile (XHToken/llama.cpp,
     which includes Spark architecture support):
       huggingface-cli download XHToken/Spark-X2.5-4B --local-dir spark-src
       # then run convert + quantize from the built llama.cpp image

See models/README.md for full instructions and license notes.
--------------------------------------------------------------------------------
EOF
  exit 2
fi

echo
echo "Model acquisition complete."
sha256sum "$QWEN_PATH" "$SPARK_PATH" 2>/dev/null | sed "s#$ROOT/##" > "$MODEL_DIR/model_sha256.txt" || true
echo "SHA256 manifest written to models/model_sha256.txt"
