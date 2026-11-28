#!/usr/bin/env bash
# One-click local CPU verification (Linux / macOS / Windows Git Bash).
# Runs all unit tests (zero GPU required) and the 10-attack anti-hack regression suite.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

echo "[verify] Using Python: $($PYTHON_BIN --version)"
echo "[verify] 1/2 Running unit tests..."
"$PYTHON_BIN" -m unittest discover -s tests -v

echo "[verify] 2/2 Running 10-attack adversarial anti-hack suite..."
"$PYTHON_BIN" -m oca.adversarial

echo "[verify] ALL CHECKS PASSED."
