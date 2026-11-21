"""Publish the locked cache from a CPU worker to an already authorized Drive mount."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import time
import uuid

from .contracts import MODEL, ROOT
from .native_colab import (Rejected, check_daemon, check_hash, check_sizes, fetch_one,
                          local_storage, need, seconds_left, stage_image, trusted_env)

LOCK = ROOT / "protocol" / "native-colab-cache.json"
PREFIX = "OpenCodeCache"
MARKER = "READY"
FUSE_FILESYSTEMS = {"fuse.rclone", "fuse.drive", "fuse.drivefs"}


@dataclass(frozen=True)
class Mount:
    path: str
    mount_id: str
    device: str
    filesystem: str
    source: str
    read_only: bool


def read_mount(path, mountinfo=None):
    path = path.resolve()
    if mountinfo is None:
        mountinfo = Path("/proc/self/mountinfo").read_text()
    matches = []

    def unescape(value):
        return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), value)

    for line in mountinfo.splitlines():
        header, trailer = line.split(" - ", 1)
        fields, target = header.split(), trailer.split()
        if unescape(fields[4]) == str(path):
            matches.append(Mount(str(path), fields[0], fields[2], target[0], unescape(target[1]),
                                 "ro" in fields[5].split(",")))
    need(len(matches) == 1 and matches[0].filesystem in FUSE_FILESYSTEMS, "mount",
         f"expected an explicit Drive FUSE mount point: {path}")
    return matches[0]


def validate_owner(proof, expected_owner, writer, reader):
    need(proof.get("schema_version") == 1 and isinstance(expected_owner, str) and bool(expected_owner.strip())
         and proof.get("owner_id") == expected_owner and proof.get("private") is True, "owner",
         "orchestrator proof does not attest the expected private Drive owner")
    need(proof.get("write_mount") == asdict(writer) and proof.get("read_mount") == asdict(reader)
         and not writer.read_only and reader.read_only
         and writer.mount_id != reader.mount_id and writer.device != reader.device, "mount",
         "proof must bind a writable mount and an independent read-only mount")
    root_id = proof.get("drive_root_id")
    need(isinstance(root_id, str) and bool(root_id.strip()) and root_id == proof.get("read_drive_root_id")
         and proof.get("uncached_readback") is True, "owner",
         "orchestrator must confirm the same private Drive root and uncached provider readback")
    available = proof.get("available_bytes")
    need(type(available) is int and available >= 0, "space", "missing verified Drive free bytes")
    return available


@contextmanager
def pinned_mount(mount):
    fd = os.open(mount.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        device = os.fstat(fd).st_dev
        need(f"{os.major(device)}:{os.minor(device)}" == mount.device, "mount", "mount device changed")
        check = lambda: need(read_mount(Path(mount.path)) == mount, "mount", "Drive mount changed during staging")
        check()
        yield Path(f"/proc/self/fd/{fd}"), check
    finally:
        os.close(fd)


def safe_path(root, relative):
    relative = PurePosixPath(relative)
    need(bool(relative.parts) and not relative.is_absolute() and ".." not in relative.parts,
         "path", "invalid cache-relative path")
    path = root
    for part in relative.parts:
        path /= part
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            continue
        need(not stat.S_ISLNK(mode), "path", f"unexpected symlink at {part}")
    return path


def marker_bytes(manifest_sha, revision, rows):
    return (json.dumps({"status": "READY", "manifest_sha256": manifest_sha, "revision": revision,
                        "file_count": len(rows), "bytes": sum(row["bytes"] for row in rows)},
                       sort_keys=True) + "\n").encode()


def file_ready(root, relative, size, deadline):
    """Wait for a fresh provider view after a remote rename."""
    while True:
        path = safe_path(root, relative)
        if path.exists():
            need(path.is_file(), "drive_readback", f"unexpected remote file type: {relative}")
            observed = path.stat().st_size
            need(observed <= size, "integrity", f"remote file is larger than its lock: {relative}")
            if observed == size:
                return path
        remaining = seconds_left(deadline, "drive_readback")
        time.sleep(min(0.5, remaining))


def publish_file(writer, reader, relative, row, source, check, deadline, readback_seconds):
    check()
    final = safe_path(writer, relative)
    final.parent.mkdir(parents=True, exist_ok=True)
    partial = final.with_name(f".{final.name}.{uuid.uuid4().hex}.part")
    try:
        with source.open("rb") as data, partial.open("xb") as out:
            while block := data.read(4 * 1024 * 1024):
                seconds_left(deadline)
                out.write(block)
        check()
        need(not final.exists(), "concurrency", "another writer changed the cache version")
        partial.replace(final)
    finally:
        with suppress(FileNotFoundError):
            partial.unlink()
    check()
    end = min(deadline, time.monotonic() + readback_seconds)
    verified = file_ready(reader, relative, row["bytes"], end)
    check_hash(verified, row, end)


def publish_cache(cache, writer, reader, version, rows, ready, expected_free, check,
                  deadline, *, readback_seconds=60, on_file=lambda _path: None, prepare=lambda _rows: None):
    check()
    version_dir = f"{PREFIX}/{version}"
    marker = f"{version_dir}/{MARKER}"
    existing_ready = safe_path(reader, marker)
    sealed = existing_ready.exists()
    if sealed:
        need(existing_ready.is_file() and existing_ready.stat().st_size == len(ready)
             and existing_ready.read_bytes() == ready, "ready", "existing READY does not match the cache lock")
    missing = []
    for row in rows:
        relative = f"{version_dir}/{row['path']}"
        path = safe_path(reader, relative)
        if path.exists():
            need(path.is_file() and path.stat().st_size == row["bytes"], "integrity",
                 f"remote file type or size differs from the lock: {row['path']}")
            check_hash(path, row, deadline)
        else:
            need(not sealed, "ready", "READY exists but a locked remote file is absent")
            need(not safe_path(writer, relative).exists(), "drive_readback",
                 f"writer has a file that the independent readback cannot see: {row['path']}")
            missing.append(row)
    if sealed:
        check()
        return {"reused": len(rows), "uploaded": 0, "ready": marker}
    need(not safe_path(writer, marker).exists(), "drive_readback", "READY is visible only in the writer")
    needed = sum(row["bytes"] for row in missing) + len(ready)
    need(min(expected_free, shutil.disk_usage(writer).free) >= needed, "space",
         f"Drive requires {needed} free bytes after reusing completed files")
    prepare(missing)
    check_sizes(cache, missing)
    # Validate every input before writing any new byte to Drive.
    for row in missing:
        check_hash(safe_path(cache, row["path"]), row, deadline)
    for row in missing:
        publish_file(writer, reader, f"{version_dir}/{row['path']}", row,
                     safe_path(cache, row["path"]), check, deadline, readback_seconds)
        on_file(row["path"])
    with tempfile.TemporaryDirectory(prefix="oca-ready-") as temp:
        proof = Path(temp) / MARKER
        proof.write_bytes(ready)
        publish_file(writer, reader, marker, {"path": marker, "bytes": len(ready),
                     "sha256": hashlib.sha256(ready).hexdigest()}, proof, check, deadline, readback_seconds)
    return {"reused": len(rows) - len(missing), "uploaded": len(missing), "ready": marker}


def prepare_public(cache, files, image, home, deadline):
    remaining = 0
    for row in [*files, *([image] if image is not None else [])]:
        final = safe_path(cache, row["path"])
        if not final.is_file():
            partial = final.with_name("." + final.name + ".part")
            need(not partial.is_symlink(), "path", "unexpected local download partial symlink")
            present = partial.stat().st_size if partial.is_file() and row is not image else 0
            need(present <= row["bytes"], "integrity", f"oversized partial: {row['path']}")
            remaining += row["bytes"] - present
    need(shutil.disk_usage(cache).free >= remaining, "space", "insufficient local download space")
    env = trusted_env(home)
    if image is not None and not safe_path(cache, image["path"]).is_file():
        docker = check_daemon(home, deadline, env)
        stage_image(docker, cache, image, deadline, env)
    # An authorized native CPU worker downloads directly, without inheriting a laptop proxy.
    env.update({key: os.environ[key] for key in ("SSL_CERT_FILE", "SSL_CERT_DIR", "CURL_CA_BUNDLE")
                if key in os.environ})
    with ThreadPoolExecutor(max_workers=6) as pool:
        pending = [pool.submit(fetch_one, cache, row, deadline, env)
                   for row in sorted(files, key=lambda row: -row["bytes"])
                   if not safe_path(cache, row["path"]).is_file()]
        for result in pending:
            result.result()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--describe-mount", type=Path)
    parser.add_argument("--write-mount", type=Path)
    parser.add_argument("--read-mount", type=Path)
    parser.add_argument("--owner-proof", type=Path)
    parser.add_argument("--expected-owner")
    parser.add_argument("--local-cache", type=Path)
    parser.add_argument("--fetch-public", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args()
    if args.describe_mount:
        print(json.dumps(asdict(read_mount(args.describe_mount))))
        return
    if not all((args.write_mount, args.read_mount, args.owner_proof, args.expected_owner, args.local_cache)):
        parser.error("both mounts, owner proof, expected owner and local cache are required")
    need(args.timeout_seconds > 0, "deadline", "timeout must be positive")
    deadline = time.monotonic() + args.timeout_seconds
    writer, reader = read_mount(args.write_mount), read_mount(args.read_mount)
    local_storage(args.owner_proof.resolve().parent)
    need(args.owner_proof.is_file() and not args.owner_proof.is_symlink()
         and args.owner_proof.stat().st_size <= 16384, "owner", "expected a small local owner proof")
    available = validate_owner(json.loads(args.owner_proof.read_text()), args.expected_owner, writer, reader)
    cache = args.local_cache.resolve()
    local_storage(cache)
    cache.mkdir(parents=True, exist_ok=True)
    raw = LOCK.read_bytes()
    manifest = json.loads(raw)
    revision = manifest["model_revision"]
    need(revision == MODEL["revision"] and manifest["model_id"] == MODEL["id"], "manifest", "model lock differs")
    sha = hashlib.sha256(raw).hexdigest()
    version = f"qwen3-8b-{revision[:8]}-497c800-{sha[:12]}"
    rows = [*manifest["files"], manifest["docker"]]
    ready = marker_bytes(sha, revision, rows)
    lock_path = safe_path(cache, ".stage-to-drive.lock")
    with lock_path.open("a") as lock, pinned_mount(writer) as w, pinned_mount(reader) as r:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Rejected("concurrency", "this CPU cache already has a staging worker") from None
        with tempfile.TemporaryDirectory(prefix="oca-cloud-stage-") as home:
            def check():
                w[1]()
                r[1]()

            def prepare(missing):
                if args.fetch_public and missing:
                    image = manifest["docker"]
                    prepare_public(cache, [row for row in missing if row is not image],
                                   image if image in missing else None, Path(home), deadline)

            report = publish_cache(cache, w[0], r[0], version, rows, ready, available, check, deadline,
                                   prepare=prepare, on_file=lambda name: print(f"Verified on Drive: {name}", flush=True))
    print(json.dumps({**report, "manifest_sha256": sha, "version": version}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (Rejected, OSError, ValueError, KeyError, TypeError) as exc:
        gate = exc.gate if isinstance(exc, Rejected) else "stage"
        raise SystemExit(json.dumps({"status": "stopped", "gate": gate, "detail": str(exc)})) from None
