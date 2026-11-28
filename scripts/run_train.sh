#!/usr/bin/env bash
# One-click single-GPU colocated V5 Agentic RL training (Dr.GRPO + Dual-Ratio TIS-Clip + 248-Module LoRA).
# Usage examples:
#   bash scripts/run_train.sh                                 # Default: Pi harness, 50 steps, seed 2026
#   HARNESS=opencode STEPS=50 LORA_SEED=2026 bash scripts/run_train.sh
#   HARNESS=pi LORA_SEED=2027 OUT_DIR=./runs/v5_pi_s2 bash scripts/run_train.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export OCA_HOME="${OCA_HOME:-$HOME/.cache/oca}"
HARNESS="${HARNESS:-pi}"
STEPS="${STEPS:-50}"
LORA_SEED="${LORA_SEED:-2026}"
LOSS_MODE="${LOSS_MODE:-tis_clip}"
ADV_MODE="${ADV_MODE:-dr_grpo}"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/runs/v5_${HARNESS}_${LOSS_MODE}_s${LORA_SEED}}"

if [ ! -d "$REPO_ROOT/data/swe_smith_v1" ]; then
  echo "[run_train] Building SWE-smith-py multi-file training pool (zero overlap with SWE-bench_Verified)..."
  python3 -u -m oca.benchmarks.swe_smith_train
fi

echo "[run_train] Starting colocated RL: harness=$HARNESS steps=$STEPS loss=$LOSS_MODE adv=$ADV_MODE out=$OUT_DIR"
python3 -u -m oca.train \
  --config protocol/oca-v5.json \
  --mode train \
  --harness "$HARNESS" \
  --task-ids-file protocol/screen_v5_multifile.json \
  --steps "$STEPS" \
  --lora-init-seed "$LORA_SEED" \
  --loss-mode "$LOSS_MODE" \
  --adv-mode "$ADV_MODE" \
  --use-deltanet-lora \
  --dynamic-sampling \
  --curriculum \
  --out-dir "$OUT_DIR"

echo "[run_train] DONE -> $OUT_DIR/checkpoints/step_$(printf '%03d' "$STEPS")"
