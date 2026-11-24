"""Pack the lean `oca` repo + cleaned tasks into a compact tar.gz for Colab G4 execution.

Normalizes all text files to Unix LF (`\\n`) inside the archive so Windows CRLF checkouts
never break exact-match `edit` tool calls inside Linux coding harnesses (OpenCode / Pi).
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import tarfile

from .. import ROOT

INCLUDE_PATHS = ("oca", "protocol", "tasks", "grader", "data", "tests", "README.md", "NOTICE", "pyproject.toml")
EXCLUDE_NAMES = {"__pycache__", ".pytest_cache", ".cache", ".git"}
TEXT_EXTS = {".py", ".md", ".json", ".toml", ".cfg", ".txt", ".sh", ".ini", ".yaml", ".yml", ".typed"}


def pack_repo(out_path: Path) -> tuple[int, int]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_files = 0
    with tarfile.open(out_path, "w:gz") as tf:
        def _add_file(fp: Path, arcname: str):
            nonlocal n_files
            if fp.suffix.lower() in TEXT_EXTS or fp.name in ("NOTICE", "README.md"):
                raw = fp.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                ti = tarfile.TarInfo(name=arcname)
                ti.size = len(raw)
                ti.mtime = int(fp.stat().st_mtime)
                ti.mode = 0o755 if fp.suffix.lower() == ".sh" else 0o644
                tf.addfile(ti, io.BytesIO(raw))
            else:
                tf.add(fp, arcname=arcname)
            n_files += 1

        for name in INCLUDE_PATHS:
            p = ROOT / name
            if not p.exists():
                continue
            if p.is_file():
                _add_file(p, name)
                continue
            for fp in sorted(p.rglob("*")):
                if any(part in EXCLUDE_NAMES for part in fp.parts):
                    continue
                if fp.is_file():
                    _add_file(fp, fp.relative_to(ROOT).as_posix())
    return n_files, out_path.stat().st_size


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts" / "oca_repo.tar.gz")
    args = ap.parse_args()
    n, sz = pack_repo(args.out)
    print(f"Packed {n} LF-normalized files -> {args.out} ({sz / 1024:.1f} KiB)")


if __name__ == "__main__":
    main()
