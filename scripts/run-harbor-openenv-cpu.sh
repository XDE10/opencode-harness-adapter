#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
python_bin="${OCA_UPSTREAM_PYTHON:?set an absolute path to the local Python with the pinned CPU requirements}"
[[ "$python_bin" = /* && -x "$python_bin" ]]
safe_dir=$(mktemp -d /tmp/oca-cpu-host-XXXXXX)
trap 'rm -rf -- "$safe_dir"' EXIT
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME="$safe_dir" XDG_CACHE_HOME="$safe_dir" \
  HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 LITELLM_LOCAL_MODEL_COST_MAP=True \
  PYTHONPATH="$root/harness" "$python_bin" -u -m colab.offline_runner
