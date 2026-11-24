"""Pack the lean `oca` repo + cleaned tasks into a compact tar.gz for Colab G4 execution."""
from __future__ import annotations

import argparse
from pathlib import Path
import tarfile

from .. import ROOT

INCLUDE_PATHS = ("oca", "protocol", "tasks", "grader", "data", "tests", "README.md", "NOTICE")
EXCLUDE_NAMES = {"__pycache__", ".pytest_cache", ".cache", ".git"}


def pack_repo(out_path: Path) -> tuple[int, int]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_files = 0
    with tarfile.open(out_path, "w:gz") as tf:
        for name in INCLUDE_PATHS:
            p = ROOT / name
            if not p.exists():
                continue
            if p.is_file():
                tf.add(p, arcname=name)
                n_files += 1
                continue
            for fp in sorted(p.rglob("*")):
                if any(part in EXCLUDE_NAMES for part in fp.parts):
                    continue
                if fp.is_file():
                    tf.add(fp, arcname=fp.relative_to(ROOT).as_posix())
                    n_files += 1
    return n_files, out_path.stat().st_size


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts" / "oca_repo.tar.gz")
    args = ap.parse_args()
    n, sz = pack_repo(args.out)
    print(f"Packed {n} files -> {args.out} ({sz / 1024:.1f} KiB)")


if __name__ == "__main__":
    main()
