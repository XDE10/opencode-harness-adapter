"""Cache the fixed, public Qwen3-8B snapshot over unauthenticated HTTPS."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from .contracts import MODEL, ROOT, digest, require

PUBLIC_SIZES = ROOT / "protocol" / "qwen3-8b-public-sizes.json"
PROXY_AND_CA = (
    "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "all_proxy",
    "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR", "CURL_CA_BUNDLE",
)


def manifest():
    public = json.loads(PUBLIC_SIZES.read_text())
    sizes = public["sizes_bytes"]
    require((public["repo_id"], public["revision"]) == (MODEL["id"], MODEL["revision"])
            and sizes.keys() == MODEL["files"].keys()
            and all(type(size) is int and size > 0 for size in sizes.values()), "size manifest differs from model lock")
    return {"repo_id": MODEL["id"], "revision": MODEL["revision"], "total_bytes": sum(sizes.values()),
            "files": [{"name": name, "size_bytes": sizes[name], "sha256": sha}
                      for name, sha in MODEL["files"].items()]}


def present_bytes(path, size):
    require(not path.is_symlink(), f"expected a regular file: {path.name}")
    if not path.exists():
        return 0
    require(path.is_file(), f"expected a regular file: {path.name}")
    count = path.stat().st_size
    require(count <= size, f"wrong file size: {path.name}")
    return count


def verify(path, info):
    require(present_bytes(path, info["size_bytes"]) == info["size_bytes"], f"size mismatch: {path.name}")
    require(digest(path) == info["sha256"], f"SHA-256 mismatch: {path.name}")


def transfer(directory, info, url, curl, env):
    name, size = info["name"], info["size_bytes"]
    final, partial = directory / name, directory / ("." + name + ".part")
    if final.exists():
        verify(final, info)
        return {"name": name, "bytes": size, "cache_hit": True}
    started = time.monotonic()
    if present_bytes(partial, size) < size:
        # The operating environment may provide its regular public HTTPS proxy. Curl reads no
        # user configuration or netrc, and receives no model-service credentials.
        result = subprocess.run([curl, "-q", "--proto", "=https", "--proto-redir", "=https", "-fsSL",
                                 "--connect-timeout", "25", "--max-time", "1200", "--speed-limit", "32768",
                                 "--speed-time", "60", "--max-filesize", str(size), "--continue-at", "-",
                                 "-o", str(partial), f"{url}/{name}?download=1"],
                                env=env, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"{name}: curl {result.returncode}: {result.stderr.strip()}")
    verify(partial, info)
    partial.replace(final)
    return {"name": name, "bytes": size, "cache_hit": False, "seconds": round(time.monotonic() - started, 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, nargs="?", help="absolute destination, omit to print the manifest")
    args = parser.parse_args()
    expected = manifest()
    if args.snapshot is None:
        print(json.dumps(expected, indent=2))
        return
    directory = args.snapshot
    require(directory.is_absolute(), "use an absolute cache directory")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    require(directory.is_dir() and not directory.is_symlink(), "expected a cache directory")
    needed = 0
    for info in expected["files"]:
        name, size = info["name"], info["size_bytes"]
        final = directory / name
        if final.exists():
            require(present_bytes(final, size) == size, f"unexpected existing size: {name}")
        else:
            needed += size - present_bytes(directory / ("." + name + ".part"), size)
    require(shutil.disk_usage(directory).free >= needed + 256 * 1024 ** 2,
            f"insufficient space for {needed} missing bytes plus verification headroom")
    curl = shutil.which("curl")
    require(curl is not None, "curl is needed for the public snapshot prefetch")
    env = {key: os.environ[key] for key in PROXY_AND_CA if key in os.environ}
    url = f"https://huggingface.co/{expected['repo_id']}/resolve/{expected['revision']}"
    failures = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        for future in as_completed([executor.submit(transfer, directory, info, url, curl, env)
                                    for info in expected["files"]]):
            try:
                print(json.dumps(future.result()), flush=True)
            except (OSError, RuntimeError, ValueError) as exc:
                print(exc, flush=True)
                failures.append(exc)
    if failures:
        parser.exit(1, f"{len(failures)} public files could not be verified\n")
    print(json.dumps({"status": "verified", "total_bytes": expected["total_bytes"]}), flush=True)


if __name__ == "__main__":
    main()
