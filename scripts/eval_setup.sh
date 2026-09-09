#!/usr/bin/env bash
# Clone/pin the external capability-evaluation benchmarks into .cache/evals/
# at the exact commits recorded in evals/config.json. External repos are NOT
# vendorized into this repository. Idempotent: skips repos already at the
# pinned commit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
CACHE="$ROOT/.cache/evals"
mkdir -p "$CACHE"

# Benchmark dir name -> config.json key. Only these get cloned; mini-swe-agent
# and harbor are installed separately (python packages / git clone).
CLONE_MAP="$(
  "$PY" - "$ROOT/evals/config.json" <<'EOF'
import json, sys
cfg = json.load(open(sys.argv[1]))
for key, b in cfg["benchmarks"].items():
    repo = b.get("repo")
    if not repo or not b.get("commit"):
        continue
    name = repo.rstrip("/").split("/")[-1].removesuffix(".git")
    print(f"{key}\t{name}\t{repo}\t{b['commit']}")
EOF
)"

while IFS=$'\t' read -r key name repo commit; do
  [ -z "$key" ] && continue
  dest="$CACHE/$name"
  if [ -d "$dest/.git" ]; then
    cur="$(git -C "$dest" rev-parse HEAD 2>/dev/null || true)"
    if [ "$cur" = "$commit" ]; then
      echo "OK   $name @ $commit (cached)"
      continue
    fi
    echo "UPDATE $name ($cur -> $commit)"
    git -C "$dest" fetch --depth 1 origin "$commit" 2>/dev/null || git -C "$dest" fetch origin "$commit"
    git -C "$dest" checkout -q "$commit"
  else
    echo "CLONE $name @ $commit"
    git clone -q --filter=blob:none "https://github.com/${repo#https://github.com/}" "$dest"
    git -C "$dest" checkout -q "$commit"
  fi
done <<< "$CLONE_MAP"

echo "All benchmarks pinned under $CACHE"
