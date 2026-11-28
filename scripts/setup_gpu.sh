#!/usr/bin/env bash
# One-click GPU environment bootstrap on any Linux single-GPU node (RTX PRO 6000 96G / A100 80G / H100 80G / Colab).
# All paths are configurable via env vars (zero hardcoded /content/ assumptions):
#   OCA_HOME        (default: ~/.cache/oca)
#   OCA_MODEL_ID    (default: Qwen/Qwen3.5-9B)
#   OCA_HF_ADAPTERS (default: XDE10/Qwen3.5-9B-Harness-Adapters-v5)
#   DOWNLOAD_ADAPTER=1 to also download the recommended pretrained `soup_v5_pi_qr_svd` adapter from HuggingFace.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export OCA_HOME="${OCA_HOME:-$HOME/.cache/oca}"
export OCA_TOOLS_DIR="${OCA_TOOLS_DIR:-$OCA_HOME/tools}"
export OCA_MODEL_ID="${OCA_MODEL_ID:-Qwen/Qwen3.5-9B}"
export OCA_MODEL_PATH="${OCA_MODEL_PATH:-$OCA_HOME/models/qwen35-9b}"
export OCA_HF_ADAPTERS="${OCA_HF_ADAPTERS:-XDE10/Qwen3.5-9B-Harness-Adapters-v5}"
DOWNLOAD_ADAPTER="${DOWNLOAD_ADAPTER:-1}"

mkdir -p "$OCA_HOME/models" "$OCA_TOOLS_DIR" "$OCA_HOME/adapters"

echo "[setup_gpu] 1/5 Installing package with GPU extras..."
python3 -m pip install -q -e ".[gpu]"

echo "[setup_gpu] 2/5 Installing unmodified coding CLI harnesses into $OCA_TOOLS_DIR..."
if command -v npm >/dev/null 2>&1; then
  if [ ! -x "$OCA_TOOLS_DIR/opencode/bin/opencode" ]; then
    npm install -g --prefix "$OCA_TOOLS_DIR/opencode" --no-audit --no-fund @opencode/cli@2.2.7
  fi
  if [ ! -x "$OCA_TOOLS_DIR/pi/bin/pi" ]; then
    npm install -g --prefix "$OCA_TOOLS_DIR/pi" --no-audit --no-fund @earendil-works/pi-coding-agent \
      || npm install -g --prefix "$OCA_TOOLS_DIR/pi" --no-audit --no-fund @mariozechner/pi-coding-agent
  fi
  chmod -R a+rX "$OCA_TOOLS_DIR"
else
  echo "[setup_gpu] WARNING: npm not found; install Node.js >= 20 to provision opencode & pi CLIs." >&2
fi

if ! command -v mini >/dev/null 2>&1; then
  python3 -m pip install -q mini-swe-agent || echo "[setup_gpu] WARNING: mini-swe-agent install skipped." >&2
fi

echo "[setup_gpu] 3/5 Downloading base model ($OCA_MODEL_ID -> $OCA_MODEL_PATH)..."
HF_HUB_ENABLE_HF_TRANSFER=1 python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('$OCA_MODEL_ID', local_dir='$OCA_MODEL_PATH', ignore_patterns=['*.msgpack', '*.h5'])
"

if [ "$DOWNLOAD_ADAPTER" = "1" ]; then
  echo "[setup_gpu] 4/5 Downloading recommended V5 adapter (soup_v5_pi_qr_svd) from $OCA_HF_ADAPTERS..."
  HF_HUB_ENABLE_HF_TRANSFER=1 python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('$OCA_HF_ADAPTERS', local_dir='$OCA_HOME/adapters', allow_patterns=['adapters/soup_v5_pi_qr_svd/*'])
"
fi

echo "[setup_gpu] 5/5 Verifying CPU unit tests..."
bash "$REPO_ROOT/scripts/verify.sh"

echo ""
echo "[setup_gpu] READY! Export these if you run commands manually:"
echo "  export OCA_HOME=\"$OCA_HOME\""
echo "  export OCA_MODEL_PATH=\"$OCA_MODEL_PATH\""
echo "  export PATH=\"$OCA_TOOLS_DIR/opencode/bin:$OCA_TOOLS_DIR/pi/bin:\$PATH\""
