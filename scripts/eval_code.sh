#!/usr/bin/env bash
# Run the full EvalPlus direct-coding suite (HumanEval + MBPP) for every
# current model, serially (GPU is shared). Resumes from cached samples.
# Long-running: run inside tmux so it survives session restarts.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${EVALPY:-$ROOT/.venv-eval/bin/python}"
LOG="$ROOT/.agent/eval_code.log"
mkdir -p "$ROOT/.agent"

MODELS="qwen3_8b deepseek_r1_8b glm4_9b yi_15_9b spark_llama"
DATASETS="humaneval mbpp"

echo "[$(date +%F\ %T)] eval_code started (models: $MODELS)" >> "$LOG"

for a in $MODELS; do
  for d in $DATASETS; do
    echo "[$(date +%F\ %T)] $a $d" >> "$LOG"
    if ! "$PY" evals/direct_code.py run "$a" "$d" >> "$LOG" 2>&1; then
      echo "[$(date +%F\ %T)] FAILED $a $d (continuing)" >> "$LOG"
    fi
  done
  "$PY" evals/runner.py stop "$a" >> "$LOG" 2>&1 || true
done

echo "[$(date +%F\ %T)] eval_code complete" >> "$LOG"
# regenerate the capability dashboard data once all direct-coding results exist
"$PY" scripts/eval_report.py >> "$LOG" 2>&1 || true
python3 scripts/generate_current_report.py >> "$LOG" 2>&1 || true
echo "[$(date +%F\ %T)] report regenerated" >> "$LOG"
