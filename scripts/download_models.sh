#!/usr/bin/env bash
# Download / verify benchmark artifacts into models/ (never committed).
# Usage: ./scripts/download_models.sh [model_id ...] (default: published cohorts)
#
# Mainstream 8-9B: download the pinned IQ4_XS GGUFs from their recorded
# Bartowski source repos, rename to the local names, and verify SHA256.
# Spark reference: download the official FP16 GGUF, quantize to IQ4_XS with the
# pinned XHToken fork's llama-quantize, and verify SHA256.
#
# Model metadata (source repo, source file, SHA256, quantization) comes from
# configs/models.json, not a hardcoded list. Existing valid files are skipped;
# a checksum mismatch is fatal.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${MODEL_DIR:-$ROOT/models}"
STAGING_DIR="${STAGING_DIR:-$ROOT/.agent/model-staging}"
SPARK_IMAGE="spark-x25-llama:cuda13"
mkdir -p "$MODEL_DIR" "$STAGING_DIR"

need(){ command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing $1" >&2; exit 1; }; }
for c in python3 curl sha256sum; do need "$c"; done

verify(){
  local file="$1" want="$2"
  [[ -s "$file" ]] || return 1
  [[ "$(sha256sum "$file" | awk '{print $1}')" == "$want" ]]
}

# download <repo> <file> <dest> <revision> [blob_url] — resumable.
download(){
  local repo="$1" file="$2" dest="$3" revision="$4" blob_url="${5:-}"
  if [[ -n "$blob_url" ]]; then
    curl -fL --retry 5 --retry-delay 3 -C - "$blob_url" -o "$dest.part"
    mv "$dest.part" "$dest"
  elif command -v hf >/dev/null 2>&1; then
    hf download "$repo" "$file" --revision "$revision" --local-dir "$(dirname "$dest")" >/dev/null
  else
    curl -fL --retry 5 --retry-delay 3 -C - \
      "https://huggingface.co/$repo/resolve/$revision/$file?download=true" -o "$dest.part"
    mv "$dest.part" "$dest"
  fi
}

# Manifest lines: local_file, repo, source_file, sha256, quantize_from_f16, revision, blob_url.
manifest="$(python3 - "$ROOT" "$@" <<'PYTHON'
import sys
sys.path.insert(0, sys.argv[1])
from bench.config import admission_models

for m in admission_models(sys.argv[2:]):
    print("\t".join([
        m["gguf_filename"],
        m["gguf_source"],
        m["gguf_source_file"],
        m["sha256"],
        "1" if m.get("quantize_from_f16") else "0",
        m.get("gguf_source_revision", "main"),
        m.get("gguf_blob_url", ""),
    ]))
PYTHON
)"

while IFS=$'\t' read -r local repo src sha q16 revision blob_url; do
  [[ -n "$local" ]] || continue
  dest="$MODEL_DIR/$local"

  if [[ "$q16" == "1" ]]; then
    # Spark reference: FP16 -> IQ4_XS via the pinned fork's llama-quantize.
    if verify "$dest" "$sha"; then
      echo "OK   $local present and verified"
      continue
    fi
    echo "== Spark reference: quantizing $repo/$src -> $local (IQ4_XS) =="
    f16="$STAGING_DIR/$src"
    [[ -s "$f16" ]] || download "$repo" "$src" "$f16" "$revision"
    [[ -s "$f16" ]] || { echo "ERROR: failed to obtain $src" >&2; exit 1; }
    docker image inspect "$SPARK_IMAGE" >/dev/null 2>&1 || {
      echo "ERROR: image $SPARK_IMAGE not built — run './scripts/build.sh' first" >&2
      exit 1
    }
    docker run --rm -v "$MODEL_DIR:/models:rw" -v "$STAGING_DIR:/staging:ro" \
      --entrypoint /src/build/bin/llama-quantize "$SPARK_IMAGE" \
      "/staging/$src" "/models/$local" IQ4_XS
  else
    # Verify the staged download before replacing the local model.
    if verify "$dest" "$sha"; then
      echo "OK   $local present and verified"
      continue
    fi
    echo "== Downloading $local from $repo =="
    tmp="$STAGING_DIR/$src"
    [[ -s "$tmp" ]] || download "$repo" "$src" "$tmp" "$revision" "$blob_url"
    if ! verify "$tmp" "$sha"; then
      echo "ERROR: SHA256 mismatch for staged $src; remove it and retry" >&2
      exit 1
    fi
    mv -f "$tmp" "$dest"
    echo "OK   $local verified (sha256 match)"
    continue
  fi

  if verify "$dest" "$sha"; then
    echo "OK   $local verified (sha256 match)"
  else
    echo "ERROR: SHA256 mismatch for $local — delete it and retry" >&2
    echo "  expected: $sha" >&2
    echo "  got:      $(sha256sum "$dest" | awk '{print $1}')" >&2
    exit 1
  fi
done <<< "$manifest"

echo
echo "Model acquisition complete."
