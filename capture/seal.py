"""Seal synthetic evidence with local content hashes, not a training signature."""

import hashlib
import json

FILES = ("trace.json", "cli-events.jsonl", "cli-stderr.txt", "cli-verification.txt", "relay.jsonl", "engine.jsonl",
         "isolation.json", "grade.json", "final.patch")
SOURCE = "synthetic_relay"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def seal(folder):
    index = {"schema_version": 1, "source": SOURCE, "trainable": False,
             "files": {name: digest(folder / name) for name in FILES}}
    save(folder / "seal.json", index)
    return index


def verify(folder):
    index = json.loads((folder / "seal.json").read_text())
    if (index["schema_version"] != 1 or index["source"] != SOURCE or index["trainable"] is not False
            or set(index["files"]) != set(FILES)):
        raise ValueError("unexpected evidence seal")
    if any(digest(folder / name) != fingerprint for name, fingerprint in index["files"].items()):
        raise ValueError("evidence digest mismatch")
    trace = json.loads((folder / "trace.json").read_text())
    if trace["source"] != SOURCE or trace["usable_for_grpo"] is not False:
        raise ValueError("unexpected trace provenance")
    return index
