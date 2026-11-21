"""Fixed CPU protocol and reproducible fixture fingerprints."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "protocol" / "cpu-v1.json"
PROTOCOL = json.loads(PIN.read_text(encoding="utf-8"))
LIMITS = PROTOCOL["limits"]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_fixtures(root=ROOT):
    for name, expected in PROTOCOL["fixture_sha256"].items():
        if sha256(root / name) != expected:
            raise RuntimeError(f"fixture differs from {PROTOCOL['id']}: {name}")
