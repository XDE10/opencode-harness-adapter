"""Portable entry for one already-authorized, independent G4. Uses an embedded source archive."""

import argparse
import base64
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.parse import urlsplit
import zipfile

PREP_SECONDS = 480
TRIAL_SECONDS = 900
UNPACK_FREE_BYTES = 22_000_000_000
CACHE_HEADROOM = 1_000_000_000
DOCKER_SOCKET = "unix:///var/run/docker.sock"
PUBLIC_HOSTS = {
    "huggingface.co", "files.pythonhosted.org", "download.pytorch.org", "download-r2.pytorch.org",
    "wheels.vllm.ai", "github.com", "registry.npmjs.org",
}
PUBLIC_ENV = ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
              "SSL_CERT_FILE", "SSL_CERT_DIR", "CURL_CA_BUNDLE")
PAYLOAD = ""


class Rejected(RuntimeError):
    def __init__(self, gate, reason):
        super().__init__(reason)
        self.gate = gate


def need(condition, gate, reason):
    if not condition:
        raise Rejected(gate, reason)


def seconds_left(deadline, gate="preparation_timeout"):
    left = (deadline() if callable(deadline) else deadline) - time.monotonic()
    need(left > 0, gate, "deadline expired")
    return left


def device_check(report, processes, minimum_vram):
    rows = [row.strip() for row in report.splitlines() if row.strip()]
    need(len(rows) == 1, "gpu", "expected exactly one visible GPU")
    try:
        name, cap, total, used, driver = (cell.strip() for cell in rows[0].split(","))
        total, used = int(total) * 1048576, int(used) * 1048576
        parts = tuple(map(int, driver.split(".")))
        driver_version = (parts + (0, 0, 0))[:3]
    except ValueError:
        raise Rejected("gpu", "invalid nvidia-smi report") from None
    need("RTX PRO 6000" in name and "Blackwell" in name and cap == "12.0" and total >= minimum_vram,
         "gpu", "expected an RTX PRO 6000 Blackwell G4, CC 12.0, with at least 90 GB visible")
    need(driver_version >= (575, 51, 3), "driver",
         "this CUDA 12.9 candidate requires NVIDIA Linux driver 575.51.03 or later")
    need(not processes.strip() and used < 2 * 1024 ** 3, "gpu_busy", "the G4 is already in use")


def trusted_env(home, source=None):
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(home), "XDG_CACHE_HOME": str(home),
           "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
           "DO_NOT_TRACK": "1", "LITELLM_LOCAL_MODEL_COST_MAP": "True", "PIP_CONFIG_FILE": "/dev/null"}
    if source is not None:
        env["PYTHONPATH"] = str(source / "harness")
    return env


def command(argv, deadline, env, gate, cap=None, *, cwd=None, log=None):
    limit = seconds_left(deadline)
    if cap is not None:
        limit = min(limit, cap)
    try:
        if log is None:
            result = subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True, timeout=limit)
        else:
            with log.open("ab") as output:
                result = subprocess.run(argv, env=env, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                        timeout=limit)
    except FileNotFoundError:
        raise Rejected(gate, f"required executable unavailable: {Path(argv[0]).name}") from None
    except subprocess.TimeoutExpired:
        raise Rejected(gate, f"timed out: {Path(argv[0]).name}") from None
    detail = "see " + log.name if log is not None else (result.stderr or result.stdout or "")[-480:].strip()
    need(result.returncode == 0, gate, f"{Path(argv[0]).name} exited {result.returncode}: {detail}")
    return result.stdout or ""


def eligible_gpu(deadline, env, minimum):
    base = ["nvidia-smi", "--format=csv,noheader,nounits"]
    query = "name,compute_cap,memory.total,memory.used,driver_version"
    rows = command([*base, "--query-gpu=" + query], deadline, env, "gpu", 5)
    active = command([*base, "--query-compute-apps=pid"], deadline, env, "gpu", 5)
    device_check(rows, active, minimum)


def local_storage(path):
    """Reject a Drive/FUSE or other network mount as the GPU's active input."""
    target = path.resolve()
    mounts = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields, details = line.split(" - ", 1)
        mount = Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), fields.split()[4]))
        if target.is_relative_to(mount):
            mounts.append((len(mount.parts), details.split()[0]))
    fs = max(mounts, default=(0, ""))[1]
    need(fs in ("overlay", "ext2", "ext3", "ext4", "xfs", "btrfs", "zfs"), "local_cache",
         "copy the Drive cache into a local disk directory before running")


def host_check():
    libc, version = platform.libc_ver()
    need(platform.system() == "Linux" and platform.machine() == "x86_64" and libc == "glibc"
         and tuple(map(int, version.split(".")[:2])) >= (2, 35) and sys.version_info[:2] >= (3, 12),
         "host", "expected Linux x86-64, glibc >= 2.35 and bootstrap Python >= 3.12")


def docker_command(home):
    config = home / "docker"
    config.mkdir(exist_ok=True)
    return ["docker", "--config", str(config), "--host", DOCKER_SOCKET]


def check_daemon(home, deadline, env):
    docker = docker_command(home)
    command([*docker, "version", "--format", "{{.Server.Version}}"], deadline, env, "docker", 8)
    return docker


def data_path(cache, row):
    path = cache / row["path"]
    need(path.resolve().is_relative_to(cache.resolve()) and not path.is_symlink(), "cache",
         f"cache path escapes the local directory: {row['path']}")
    return path


def check_sizes(cache, files):
    for row in files:
        path = data_path(cache, row)
        need(path.is_file() and path.stat().st_size == row["bytes"], "cache",
             f"missing or wrong size: {row['path']}")


def check_hash(path, row, deadline):
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        while block := file.read(4 * 1024 * 1024):
            seconds_left(deadline)
            hasher.update(block)
    need(path.stat().st_size == row["bytes"] and hasher.hexdigest() == row["sha256"], "integrity",
         f"SHA-256 or size mismatch: {row['path']}")


def check_cache(cache, files, deadline):
    check_sizes(cache, files)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda row: check_hash(data_path(cache, row), row, deadline), files))


SBOX = r"""
import os, socket
from pathlib import Path
assert os.geteuid() == 65534 and os.getegid() == 65534
assert [name for _, name in socket.if_nameindex()] == ["lo"]
assert all(x.split()[0] == "lo" for x in Path("/proc/net/route").read_text().splitlines()[1:] if x)
assert Path("/oca-probe").read_text() == "offline"
assert os.statvfs("/oca-probe").f_flag & os.ST_RDONLY
status = dict(line.split(":", 1) for line in Path("/proc/self/status").read_text().splitlines())
assert int(status["CapEff"], 16) == 0 and status["NoNewPrivs"].strip() == "1"
assert not os.path.lexists("/var/run/docker.sock")
assert not any(key in os.environ for key in ("HF_TOKEN", "OPENAI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS"))
try:
    Path("/oca-write-test").touch()
except OSError:
    pass
else:
    raise AssertionError("container root is writable")
Path("/tmp/oca-write-test").touch()
cgroups = Path("/sys/fs/cgroup")
if (cgroups / "cgroup.controllers").exists():
    memory = (cgroups / "memory.max").read_text()
    pids = (cgroups / "pids.max").read_text()
    quota, period = (cgroups / "cpu.max").read_text().split()
else:
    memory = (cgroups / "memory/memory.limit_in_bytes").read_text()
    pids = (cgroups / "pids/pids.max").read_text()
    quota = (cgroups / "cpu/cpu.cfs_quota_us").read_text()
    period = (cgroups / "cpu/cpu.cfs_period_us").read_text()
expected = (str(192 * 1024 * 1024), "32")
assert (memory.strip(), pids.strip()) == expected, (
    "effective cgroup memory/pids: " + memory.strip() + "/" + pids.strip() + "; expected 192 MiB/32"
)
assert quota.isdecimal() and int(quota) > 0 and int(quota) * 2 == int(period), (
    "effective cgroup CPU: " + quota.strip() + "/" + period.strip() + "; expected half a CPU"
)
"""


def prove_docker(docker, home, cache, image, deadline, env):
    image_id = image["image_id"]
    command([*docker, "load", "--input", str(cache / image["path"])], deadline, env, "docker_image", 120)
    got = command([*docker, "image", "inspect", "--format", "{{.Id}} {{.Os}} {{.Architecture}}",
                   image_id], deadline, env, "docker_image", 8).strip()
    need(got == image_id + " linux amd64", "docker_image", "the imported image identity differs from the lock")
    probe = home / "probe"
    probe.write_text("offline")
    probe.chmod(0o444)
    command([*docker, "run", "--rm", "--pull=never", "--network=none", "--read-only",
             "--user=65534:65534", "--cap-drop=ALL", "--security-opt=no-new-privileges",
             "--memory=192m", "--memory-swap=192m", "--cpus=0.5", "--pids-limit=32",
             "--tmpfs=/tmp:rw,nosuid,nodev,size=16m,mode=1777",
             "--mount", f"type=bind,source={probe},target=/oca-probe,readonly",
             image_id, "python", "-I", "-c", SBOX], deadline, env, "isolation", 30)


def fetch_one(cache, row, deadline, env):
    path = data_path(cache, row)
    if not path.exists():
        url = urlsplit(row["url"])
        need(url.scheme == "https" and url.hostname in PUBLIC_HOSTS and not url.username and not url.password,
             "public_source", "download URL is outside the allowed public sources")
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name("." + path.name + ".part")
        need(not partial.is_symlink(), "cache", "download partial is a symlink")
        if not partial.exists() or partial.stat().st_size < row["bytes"]:
            argv = ["curl", "-q", "--proto", "=https", "--proto-redir", "=https", "-fsSL",
                    "--connect-timeout", "12", "--speed-limit", "65536", "--speed-time", "25",
                    "--max-filesize", str(row["bytes"]), "--continue-at", "-", "-o", str(partial), row["url"]]
            try:
                child = subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                         text=True)
            except FileNotFoundError:
                raise Rejected("public_download", "curl is unavailable") from None
            try:
                while True:
                    try:
                        _, error = child.communicate(timeout=min(0.5, seconds_left(deadline)))
                        break
                    except subprocess.TimeoutExpired:
                        continue
                need(child.returncode == 0, "public_download", f"curl failed for {row['path']}: {error[:350]}")
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()
        check_hash(partial, row, deadline)
        partial.replace(path)
    else:
        check_hash(path, row, deadline)


def transfer_guard(remaining, speed, available):
    return remaining == 0 or (speed > 0 and remaining / speed <= available)


def fetch_public(cache, rows, deadline, home):
    missing = [row for row in rows if not data_path(cache, row).is_file()]
    needed = sum(row["bytes"] for row in missing)
    need(shutil.disk_usage(cache).free >= needed + CACHE_HEADROOM, "disk", "public cache will not fit")
    env = trusted_env(home) | {k: os.environ[k] for k in PUBLIC_ENV if k in os.environ}
    pending = deque(sorted(rows, key=lambda row: row["bytes"], reverse=True))
    active = set()
    download_deadline = deadline - 20
    stop = download_deadline

    def progress():
        count = 0
        for row in missing:
            path = data_path(cache, row)
            partial = path.with_name("." + path.name + ".part")
            for candidate in (path, partial):
                try:
                    count += candidate.stat().st_size
                    break
                except FileNotFoundError:
                    pass
        return count

    mark, completed = time.monotonic(), progress()
    with ThreadPoolExecutor(max_workers=12) as pool:
        try:
            while pending or active:
                seconds_left(download_deadline)
                while pending and len(active) < 12:
                    active.add(pool.submit(fetch_one, cache, pending.popleft(), lambda: stop, env))
                for done in {job for job in active if job.done()}:
                    active.remove(done)
                    done.result()
                now = time.monotonic()
                if needed and now - mark >= 45:
                    current = progress()
                    speed = (current - completed) / (now - mark)
                    print(f"Public cache {current}/{needed} bytes, {speed/1e6:.1f} MB/s", flush=True)
                    need(transfer_guard(max(0, needed - current), speed, download_deadline - now),
                         "public_throughput", "observed throughput cannot finish the remaining cache in time")
                    mark, completed = now, current
                if pending or active:
                    time.sleep(0.25)
        finally:
            stop = time.monotonic()
            for job in active:
                job.cancel()


def unpack_tool(cache, stage, row, deadline):
    archive = cache / row["path"]
    if row["path"].endswith(".tgz"):
        target = stage / ".tools" / "opencode-2.2.7" / "bin" / "opencode"
        target.parent.mkdir(parents=True)
        with tarfile.open(archive, "r:gz") as tar:
            item = tar.getmember("package/bin/opencode")
            need(item.isfile(), "install", "OpenCode archive did not contain the pinned standalone executable")
            with tar.extractfile(item) as stream, target.open("wb") as out:
                while block := stream.read(4 * 1024 * 1024):
                    seconds_left(deadline)
                    out.write(block)
        target.chmod(0o755)
    else:
        # Only the two fixed public archives reach this extraction.
        target = stage / ("cp313" if "3.13." in archive.name else "cp312")
        target.mkdir()
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar:
                seconds_left(deadline)
                tar.extract(member, target, filter="data")


def install_software(cache, source, rows, deadline, env, logs):
    for row in rows:
        if row["path"].startswith("tools/"):
            seconds_left(deadline)
            unpack_tool(cache, source, row, deadline)
    locations = {}
    for version, folder in (("cp313", "harbor-wheels"), ("cp312", "vllm-cu129-wheels")):
        python = source / version / "python" / "bin" / "python3"
        venv = source / (version + "-venv")
        command([str(python), "-m", "venv", str(venv)], deadline, env, "install", log=logs / "install.log")
        interpreter = str(venv / "bin" / "python")
        files = sorted(str(cache / row["path"]) for row in rows if row["path"].startswith(folder + "/"))
        pip = [interpreter, "-m", "pip", "--isolated", "--disable-pip-version-check",
               "install", "--no-index", "--no-deps", "--no-cache-dir", "--no-compile"]
        command([*pip, *files], deadline, env, "install", log=logs / "install.log")
        command([interpreter, "-m", "pip", "--isolated", "check"], deadline, env, "install",
                log=logs / "install.log")
        if version == "cp312":
            files = sorted(str(cache / row["path"]) for row in rows if row["path"].startswith("flashinfer-wheels/"))
            command([*pip, *files], deadline, env, "install", log=logs / "install.log")
        locations[version] = venv
    return locations["cp313"] / "bin" / "python", locations["cp312"] / "bin" / "vllm"


def trial(argv, env, source, deadline):
    limit = seconds_left(deadline, "trial_timeout")
    process = subprocess.Popen(argv, env=env, cwd=source, start_new_session=True)
    try:
        code = process.wait(timeout=limit)
        need(code == 0, "trial", f"one boundary attempt stopped with exit {code}")
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=18)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        raise Rejected("trial_timeout", "boundary attempt interrupted at the outer deadline") from None


def run_prepared(cache, output, source, manifest, deadline):
    home = source / ".trusted-home"
    home.mkdir()
    env = trusted_env(home, source)
    host_check()
    local_storage(cache)
    local_storage(output.parent)
    eligible_gpu(deadline, env, manifest["minimum_vram_bytes"])
    need(shutil.disk_usage(source).free >= UNPACK_FREE_BYTES, "disk",
         f"need at least {UNPACK_FREE_BYTES} free bytes on the local working volume after staging the cache")
    docker = check_daemon(home, deadline, env)
    files = manifest["files"]
    image = manifest["docker"]
    check_cache(cache, [*files, image], deadline)
    prove_docker(docker, home, cache, image, deadline, env)
    env["OCA_OFFLINE_DOCKER_IMAGE_ID"] = image["image_id"]
    python, vllm = install_software(cache, source, files, deadline, env, output)
    cuda_check = ("import torch; assert torch.version.cuda == '12.9'; "
                  "assert torch.cuda.is_available() and torch.cuda.get_device_capability() == (12, 0); "
                  "assert torch.cuda.is_bf16_supported(); torch.zeros(1, device='cuda', dtype=torch.bfloat16)")
    command([str(vllm.parent / "python"), "-c", cuda_check], deadline, env, "cuda", 25,
            log=output / "install.log")
    seconds_left(deadline)
    print("Local cache and Docker isolation verified. Starting one boundary trial.", flush=True)
    trial([str(python), "-u", "-m", "colab.g4_first", str(cache / "snapshot"), str(output / "trial"),
           "--vllm", str(vllm), "--allow-existing-g4"], env, source, time.monotonic() + TRIAL_SECONDS)


def stage_image(docker, cache, image, deadline, env):
    target = data_path(cache, image)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(".docker-image.tar.part")
        need(not partial.is_symlink(), "cache", "Docker export partial is a symlink")
        command([*docker, "image", "save", "--output", str(partial), image["registry_ref"]],
                deadline, env, "docker_image", 120)
        check_hash(partial, image, deadline)
        partial.replace(target)
    else:
        check_hash(target, image, deadline)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--allow-existing-g4", action="store_true")
    modes.add_argument("--prepare-public-cache", action="store_true")
    modes.add_argument("--verify-package", action="store_true")
    modes.add_argument("--verify-cache", action="store_true")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--output", type=Path, default=Path("oca-boundary-evidence"))
    args = parser.parse_args()
    deadline = time.monotonic() + PREP_SECONDS
    with zipfile.ZipFile(BytesIO(base64.b85decode(PAYLOAD))) as archive:
        manifest = json.loads(archive.read("protocol/native-colab-cache.json"))
        if args.verify_package:
            need(archive.testzip() is None, "package", "source archive is damaged")
            print(json.dumps({"status": "package_verified", "files": len(manifest["files"]),
                              "image_bytes": manifest["docker"]["bytes"]}), flush=True)
            return
        if args.cache is None:
            parser.error("--cache is required for the selected mode")
        cache = args.cache.resolve()
        output = args.output.resolve()
        if args.prepare_public_cache or args.verify_cache:
            host_check()
            if args.prepare_public_cache:
                cache.mkdir(parents=True, exist_ok=True)
            local_storage(cache)
            with tempfile.TemporaryDirectory(prefix="oca-cache-home-") as tmp:
                home = Path(tmp)
                env = trusted_env(home)
                docker = check_daemon(home, deadline, env)
                image = manifest["docker"]
                if args.prepare_public_cache:
                    needed = sum(row["bytes"] for row in [*manifest["files"], image]
                                 if not data_path(cache, row).is_file())
                    need(shutil.disk_usage(cache).free >= needed + CACHE_HEADROOM, "disk",
                         "public cache will not fit")
                    stage_image(docker, cache, image, deadline, env)
                    prove_docker(docker, home, cache, image, deadline, env)
                    fetch_public(cache, manifest["files"], deadline, home)
                else:
                    check_cache(cache, [*manifest["files"], image], deadline)
                    prove_docker(docker, home, cache, image, deadline, env)
            print("Local cache and pinned Docker isolation verified.", flush=True)
            return
        need(cache.is_dir(), "cache", "an already staged local cache directory is required")
        need(not output.exists(), "output", "use a fresh output directory")
        output.mkdir(mode=0o700, parents=True)
        with tempfile.TemporaryDirectory(prefix=".oca-job-", dir=output.parent) as tmp:
            source = Path(tmp)
            archive.extractall(source)
            try:
                run_prepared(cache, output, source, manifest, deadline)
            except Rejected as exc:
                report = {"status": "stopped", "gate": exc.gate, "detail": str(exc)}
                (output / "stop.json").write_text(json.dumps(report) + "\n")
                raise


def entry():
    try:
        main()
    except Rejected as exc:
        print(json.dumps({"status": "stopped", "gate": exc.gate, "detail": str(exc)}), flush=True)
        raise SystemExit(2) from None
