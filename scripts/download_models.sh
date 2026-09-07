#!/usr/bin/env bash
# Download / verify the current benchmark artifacts into models/ (never committed).
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

# download <repo> <file> <dest> — resumable, prefers hf when available.
download(){
  local repo="$1" file="$2" dest="$3"
  if command -v hf >/dev/null 2>&1; then
    hf download "$repo" "$file" --local-dir "$(dirname "$dest")" --local-dir-use-symlinks False >/dev/null
  else
    curl -fL --retry 5 --retry-delay 3 -C - \
      "https://huggingface.co/$repo/resolve/main/$file?download=true" -o "$dest.part"
    mv "$dest.part" "$dest"
  fi
}

# Manifest lines: local_file<TAB>repo<TAB>source_file<TAB>sha256<TAB>quantize_from_f16
manifest="$(python3 - "$ROOT" <<'PY'
import json, sys
d = json.load(open(f"{sys.argv[1]}/configs/models.json"))
for m in d["models"]:
    if not m.get("enabled"):
        continue
    if m.get("cohort") not in ("mainstream_8_9b", "spark_reference"):
        continue
    print("\t".join([
        m.get("gguf_filename", ""),
        m.get("gguf_source", "") or "",
        m.get("gguf_source_file", "") or "",
        m.get("sha256", "") or "",
        "1" if m.get("quantize_from_f16") else "0",
    ]))
PY
)"

while IFS=$'\t' read -r local repo src sha q16; do
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
    [[ -s "$f16" ]] || download "$repo" "$src" "$f16"
    [[ -s "$f16" ]] || { echo "ERROR: failed to obtain $src" >&2; exit 1; }
    docker image inspect "$SPARK_IMAGE" >/dev/null 2>&1 || {
      echo "ERROR: image $SPARK_IMAGE not built — run 'make build' first" >&2
      exit 1
    }
    docker run --rm -v "$MODEL_DIR:/models:rw" -v "$STAGING_DIR:/staging:ro" \
      --entrypoint /src/build/bin/llama-quantize "$SPARK_IMAGE" \
      "/staging/$src" "/models/$local" IQ4_XS
  else
    # Mainstream: direct download from the recorded source repo, then rename.
    if verify "$dest" "$sha"; then
      echo "OK   $local present and verified"
      continue
    fi
    echo "== Downloading $local from $repo =="
    tmp="$STAGING_DIR/$src"
    if [[ ! -s "$tmp" ]]; then
      download "$repo" "$src" "$tmp"
    fi
    [[ -s "$tmp" ]] || { echo "ERROR: failed to obtain $src" >&2; exit 1; }
    mv -f "$tmp" "$dest"
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
echo "Model acquisition complete (mainstream 8-9B + Spark reference)."
