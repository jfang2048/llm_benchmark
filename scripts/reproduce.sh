#!/usr/bin/env bash
# One-command end-to-end reproduction.
#
#   ./scripts/reproduce.sh                       # current benchmark (capacity)
#   REPRODUCE_MODE=smoke ./scripts/reproduce.sh  # fast validation path
#
# Idempotent: existing models and images are reused, not re-downloaded/rebuilt.
# Fails early with actionable messages via the preflight checker.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${REPRODUCE_MODE:-capacity}"

step(){ printf '\n===== %s =====\n' "$*"; }

step "1/7 preflight"
"$ROOT/scripts/preflight.sh"

step "2/7 download models"
"$ROOT/scripts/download_models.sh"

step "3/7 build images"
"$ROOT/scripts/build.sh"

step "4/7 deploy benchmark containers"
"$ROOT/scripts/deploy.sh"

step "5/7 startup healthcheck"
"$ROOT/scripts/healthcheck.sh"

step "6/7 benchmark (mode=$MODE)"
MODE="$MODE" "$ROOT/scripts/benchmark.sh"

step "7/7 generate report"
if [ -x "$ROOT/.venv/bin/python" ]; then
  "$ROOT/.venv/bin/python" "$ROOT/scripts/generate_v2_report.py"
else
  python3 "$ROOT/scripts/generate_v2_report.py"
fi

echo
echo "Reproduction complete. Artifacts:"
echo "  results/v2/runs/          (new benchmark run)"
echo "  results/v2/final/         (curated public dataset)"
echo "  docs/v2/index.html        (current dashboard)"
echo
echo "To curate the new run into results/v2/final/: make curate-v2"
