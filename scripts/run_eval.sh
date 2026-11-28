#!/usr/bin/env bash
# One-click paired evaluation (Base vs LoRA adapter) with automatic trajectory audit.
# Usage examples:
#   bash scripts/run_eval.sh                                        # Pi on 65-task heldout (2 seeds) with HF soup_v5_pi_qr_svd
#   HARNESS=mini_swe SPLIT=heldout SEEDS="101 102" bash scripts/run_eval.sh
#   HARNESS=pi SPLIT=swe_verified SEEDS="101 102" bash scripts/run_eval.sh
#   LORA_SPEC="my_ckpt=./runs/my_run/checkpoints/step_050" bash scripts/run_eval.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export OCA_HOME="${OCA_HOME:-$HOME/.cache/oca}"
HARNESS="${HARNESS:-pi}"
SPLIT="${SPLIT:-heldout}"
SEEDS="${SEEDS:-101 102}"
CONCURRENCY="${CONCURRENCY:-32}"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/runs/eval_${SPLIT}_${HARNESS}}"

DEFAULT_ADAPTER="$OCA_HOME/adapters/adapters/soup_v5_pi_qr_svd"
if [ -z "${LORA_SPEC:-}" ]; then
  if [ ! -d "$DEFAULT_ADAPTER" ]; then
    echo "[run_eval] Pretrained soup_v5_pi_qr_svd not found locally; downloading from HuggingFace..."
    python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('XDE10/Qwen3.5-9B-Harness-Adapters-v5', local_dir='$OCA_HOME/adapters', allow_patterns=['adapters/soup_v5_pi_qr_svd/*'])
"
  fi
  LORA_SPEC="soup_v5_pi_qr_svd=$DEFAULT_ADAPTER"
fi

if [ "$SPLIT" = "swe_verified" ] && [ ! -d "$REPO_ROOT/data/swe_verified_v1" ]; then
  echo "[run_eval] Rebuilding frozen 60-task pure-Python SWE-bench_Verified subset..."
  python3 -u -m oca.benchmarks.swe_verified --protocol protocol/swe_verified_60.json
fi

echo "[run_eval] Running paired eval: harness=$HARNESS split=$SPLIT seeds=($SEEDS) out=$OUT_DIR"
# shellcheck disable=SC2086
python3 -u -m oca.eval \
  --config protocol/oca-v5.json \
  --harness "$HARNESS" \
  --split "$SPLIT" \
  --seeds $SEEDS \
  --concurrency "$CONCURRENCY" \
  --out-dir "$OUT_DIR" \
  --lora "$LORA_SPEC"

echo "[run_eval] Running trajectory behavioral & anti-hack audit..."
python3 -u -m oca.audit_trajectories --eval-dir "$OUT_DIR"
echo "[run_eval] DONE -> $OUT_DIR/eval_report.json"
