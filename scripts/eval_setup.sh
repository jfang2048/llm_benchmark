#!/usr/bin/env bash
# Reproducible capability-evaluation environment setup.
#
# 1. Creates/updates the project-owned .venv-eval/ and installs pinned deps
#    (requirements-eval.txt) plus mini-swe-agent + swebench from their pinned
#    git clones in .cache/evals/.
# 2. Clones/pins external benchmark repos into .cache/evals/ at the exact
#    commits recorded in evals/config.json (never vendorized into this repo).
#
# Idempotent: skips repos already at the pinned commit and reuses an existing
# venv. Uses uv when available, else python -m venv.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
VENV="$ROOT/.venv-eval"
CACHE="$ROOT/.cache/evals"
mkdir -p "$CACHE"

# ---- 1. venv + pinned deps --------------------------------------------------
if [ ! -x "$VENV/bin/python" ]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.12 "$VENV"
  else
    "$PY" -m venv "$VENV"
  fi
fi
VPY="$VENV/bin/python"
VPY -m pip install --quiet --upgrade pip
VPY -m pip install --quiet -r "$ROOT/requirements-eval.txt"

# mini-swe-agent + swebench from pinned clones (exact commits).
for pkg in mini-swe-agent SWE-bench; do
  src="$CACHE/$pkg"
  if [ -d "$src" ]; then
    VPY -m pip install --quiet -e "$src"
  fi
done

# ---- 2. clone/pin external benchmarks --------------------------------------
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

echo "Capability environment ready: $VENV ; benchmarks under $CACHE"
