#!/usr/bin/env bash
# One-command end-to-end reproduction of the current benchmark.
#
#   ./scripts/reproduce.sh                       # full: both cohorts + dashboard
#   REPRODUCE_MODE=smoke ./scripts/reproduce.sh  # fast admission sanity path
#
# Idempotent: existing models and images are reused, not re-downloaded/rebuilt.
# The runner skips already-completed cells, so a resumed run continues where it
# left off.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${REPRODUCE_MODE:-full}"

# AIPerf CLI; override with AIPERF=/path/to/aiperf if not in $HOME/venvs/aiperf.
AIPERF="${AIPERF:-$HOME/venvs/aiperf/bin/aiperf}"
export AIPERF

RUNNER() { python3 -m bench.runner "$@"; }

step(){ printf '\n===== %s =====\n' "$*"; }

cd "$ROOT"

step "1/6 preflight"
"$ROOT/scripts/preflight.sh"

if [[ "$MODE" == "smoke" ]]; then
  step "smoke: admission (mainstream 8-9B + Spark reference)"
  "$ROOT/scripts/admit.sh"
  step "smoke: report"
  python3 scripts/generate_current_report.py
  echo "Smoke complete."
  exit 0
fi

step "2/6 build images"
"$ROOT/scripts/build.sh"

step "3/6 download models"
"$ROOT/scripts/download_models.sh"

step "4/6 benchmark (both cohorts, all suites)"
RUNNER --cohort mainstream_8_9b --suite capacity
RUNNER --cohort spark_reference --suite capacity
RUNNER --cohort mainstream_8_9b --suite reliability
RUNNER --cohort spark_reference --suite reliability
RUNNER --cohort mainstream_8_9b --suite shape
RUNNER --cohort spark_reference --suite shape
RUNNER --cohort mainstream_8_9b --suite startup
RUNNER --cohort spark_reference --suite startup
RUNNER --cohort mainstream_8_9b --suite soak
RUNNER --cohort spark_reference --suite soak
RUNNER --cohort mainstream_8_9b --suite open-loop
RUNNER --cohort spark_reference --suite open-loop
RUNNER --cohort mainstream_8_9b --suite sessions
RUNNER --cohort spark_reference --suite sessions
python3 -m bench.llama_bench

step "5/6 report"
python3 scripts/generate_current_report.py

step "6/6 validate"
python3 scripts/validate_config.py
"$ROOT/scripts/security_check.sh"

echo
echo "Reproduction complete. Artifacts:"
echo "  results/current/mainstream-8-9b/   curated 8-9B cohort results"
echo "  results/current/spark-reference/    curated Spark reference results"
echo "  docs/index.html                     current dashboard"
echo
echo "Commit the curated TSVs and publish with: make report && git push"
