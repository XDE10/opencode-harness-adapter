#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
./scripts/install-opencode.sh
PYTHONPATH="$root/harness" python3 -m unittest discover -s tests -v
exec python3 -u harness/run.py "$@"
