#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
./scripts/install-opencode.sh
export PYTHONPATH="$root/harness"
exec python3 -u -m capture "$@"
