#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 3 || "$3" != "--allow-existing-g4" ]]; then
  echo "Usage: $0 /absolute/snapshot /absolute/new-output-dir --allow-existing-g4" >&2
  exit 2
fi
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
python_bin="${OCA_UPSTREAM_PYTHON:?set an absolute path to the Python with pinned CPU dependencies}"
vllm_bin="${OCA_VLLM_BIN:?set an absolute path to the installed vLLM executable}"
[[ "$python_bin" = /* && -x "$python_bin" && "$vllm_bin" = /* && -x "$vllm_bin" ]]
local_home=$(mktemp -d /tmp/oca-g4-home-XXXXXX)
trap 'rm -rf -- "$local_home"' EXIT
umask 077
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME="$local_home" XDG_CACHE_HOME="$local_home" \
  HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 TRANSFORMERS_OFFLINE=1 DO_NOT_TRACK=1 \
  LITELLM_LOCAL_MODEL_COST_MAP=True PYTHONPATH="$root/harness" \
  "$python_bin" -u -m colab.g4_first "$@" --vllm "$vllm_bin"
