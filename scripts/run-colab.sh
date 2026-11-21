#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
export PYTHONPATH="$root/harness"
if [[ $# -eq 0 || "$1" == prepare ]]; then
  ./scripts/run-harness.sh
  if [[ $# -eq 0 ]]; then set -- prepare; fi
fi
exec python3 -m colab.workflow "$@"
