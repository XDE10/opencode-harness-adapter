"""Emit one Python file compatible with the Colab CLI's in-kernel execution."""

import argparse
import base64
import io
from pathlib import Path
import subprocess
import tarfile
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--revision", default="HEAD")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    data = subprocess.check_output(["git", "archive", "--format=tar", args.revision], cwd=root)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=io.BytesIO(data)) as source, zipfile.ZipFile(
            buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        for member in source:
            if member.isfile():
                entry = zipfile.ZipInfo(member.name)
                entry.external_attr = member.mode << 16
                zipped.writestr(entry, source.extractfile(member).read(),
                                compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        launcher = source.extractfile("colab/native_colab.py").read()
    if args.output.exists():
        parser.error("output already exists")
    payload = base64.b85encode(buffer.getvalue()).decode("ascii")
    chunks = "\n".join("    " + repr(payload[i:i + 100]) for i in range(0, len(payload), 100))
    args.output.write_bytes(launcher + (
        "\n\nPAYLOAD = (\n" + chunks + "\n)\n\nif __name__ == '__main__':\n    entry()\n").encode())


if __name__ == "__main__":
    main()
