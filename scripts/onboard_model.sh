#!/usr/bin/env bash
# Onboard a candidate model for smoke testing.
#
# Downloads a pre-quantized Q4_K_M GGUF (onboarding/smoke path only — the final
# ranking re-quantizes from the official checkpoint via the recipe in
# docs/engine.md), verifies its SHA256, and prints the registry entry to append
# to configs/models.json.
#
# Usage:
#   ./scripts/onboard_model.sh \
#     --repo Qwen/Qwen3-4B-GGUF \
#     --file Qwen3-4B-Q4_K_M.gguf \
#     --sha256 <hex> \
#     --arm qwen_llama \
#     --name "Qwen3-4B"
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${MODEL_DIR:-$ROOT/models}"

REPO=""; FILE=""; SHA256=""; ARM=""; NAME=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="$2"; shift 2 ;;
    --file) FILE="$2"; shift 2 ;;
    --sha256) SHA256="$2"; shift 2 ;;
    --arm) ARM="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

[[ -n "$REPO" && -n "$FILE" && -n "$ARM" && -n "$NAME" ]] || {
  echo "usage: onboard_model.sh --repo <hf> --file <gguf> [--sha256 <hex>] --arm <id> --name <display>" >&2
  exit 2
}

mkdir -p "$MODEL_DIR"
URL="https://huggingface.co/${REPO}/resolve/main/${FILE}?download=true"
DEST="$MODEL_DIR/$FILE"

if [[ -s "$DEST" ]]; then
  echo "present: $DEST"
else
  echo "downloading: $URL"
  curl -fL --retry 5 --retry-delay 3 -C - "$URL" -o "$DEST.part"
  mv "$DEST.part" "$DEST"
fi

if [[ -n "$SHA256" ]]; then
  GOT="$(sha256sum "$DEST" | awk '{print $1}')"
  if [[ "$GOT" != "$SHA256" ]]; then
    echo "SHA256 MISMATCH for $FILE: got $GOT, want $SHA256" >&2
    exit 1
  fi
  echo "SHA256 verified: $FILE"
else
  echo "SHA256: $(sha256sum "$DEST" | awk '{print $1}')  (record this; no expected hash supplied)"
fi

echo
echo "Registry entry to add to configs/models.json:"
cat <<EOF
  {
    "id": "$ARM",
    "display_name": "$NAME",
    "arm": "$ARM",
    "upstream_repo": "$REPO",
    "quantization": "Q4_K_M",
    "gguf_filename": "$FILE",
    "sha256": "$(sha256sum "$DEST" | awk '{print $1}')",
    "enabled": false,
    "primary_cohort": true
  }
EOF
echo
echo "Next: smoke-test with 'MODE=smoke ./scripts/benchmark.sh' and flip 'enabled' to true only after it passes."
