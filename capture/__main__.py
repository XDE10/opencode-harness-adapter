"""Run local synthetic capture or verify an existing seal."""

import argparse
from pathlib import Path
import uuid

from .integration import run
from .seal import verify
from colab.contracts import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path, help="verify a previously sealed synthetic run")
    args = parser.parse_args()
    if args.verify:
        verify(args.verify)
        print("Synthetic seal verified; not trainable.")
    else:
        run(ROOT / "artifacts" / ("relay-cpu-" + uuid.uuid4().hex[:10]))


if __name__ == "__main__":
    main()
