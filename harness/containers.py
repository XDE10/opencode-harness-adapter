"""Run the local Docker image with a fresh container for each operation."""

import os
from pathlib import Path
import selectors
import subprocess
import tempfile
import time
import uuid
from protocol import PROTOCOL, ROOT

OFFLINE_IMAGE_ID = "sha256:4bed2b8b523314dbacb1acce4f093ff6a6039a928ed726d74f96df90b165a773"
image_override = os.environ.get("OCA_OFFLINE_DOCKER_IMAGE_ID")
if image_override not in (None, OFFLINE_IMAGE_ID):
    raise ValueError("unrecognized offline Docker image identity")
IMAGE = image_override or PROTOCOL["image"]
OUTPUT_LIMIT = 1024 * 1024


class Docker:
    def __init__(self):
        config = ROOT / ".tools" / "docker-config"
        config.mkdir(parents=True, exist_ok=True)
        # Keep Docker away from user config, credential stores and remote daemons.
        self.argv = ["docker", "--config", str(config), "--host", "unix:///var/run/docker.sock"]
        self.env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(config)}

    def invoke(self, args, *, payload=b"", timeout=20):
        """Return partial output on time/size limits without unbounded buffering."""
        stdout, stderr = bytearray(), bytearray()
        deadline = time.monotonic() + timeout
        with tempfile.TemporaryFile() as stdin, selectors.DefaultSelector() as pipes:
            stdin.write(payload)
            stdin.seek(0)
            with subprocess.Popen(self.argv + args, env=self.env, stdin=stdin,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
                pipes.register(proc.stdout, selectors.EVENT_READ, stdout)
                pipes.register(proc.stderr, selectors.EVENT_READ, stderr)
                limit = None
                while pipes.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        limit = "timeout"
                        break
                    for key, _ in pipes.select(remaining):
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            pipes.unregister(key.fileobj)
                            continue
                        key.data.extend(chunk)
                        if len(stdout) + len(stderr) > OUTPUT_LIMIT:
                            limit = "output_limit"
                            break
                    if limit:
                        break
                if limit:
                    proc.kill()
                else:
                    try:
                        proc.wait(timeout=max(0, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        limit = "timeout"
                        proc.kill()
                return limit, proc.wait(), stdout.decode(errors="replace"), stderr.decode(errors="replace")

    def prepare(self):
        _, code, _, _ = self.invoke(["image", "inspect", IMAGE])
        if code:
            limit, code, out, err = self.invoke(["pull", IMAGE], timeout=180)
            if limit or code:
                raise RuntimeError(f"Docker image pull failed ({limit or code}): {err or out}")

    @staticmethod
    def mount(source, destination, *, writable=False):
        spec = f"type=bind,source={source},target={destination}"
        return ["--mount", spec + ("" if writable else ",readonly")]

    @staticmethod
    def name(prefix):
        return f"oca-{prefix}-{uuid.uuid4().hex[:12]}"

    @staticmethod
    def sandbox(name, *, network="none", memory="192m", cpus="0.5", pids=32):
        return ["run", "--name", name, "--pull=never", "--network", network,
                "--user", "65534:65534", "--read-only", "--cap-drop=ALL",
                "--security-opt=no-new-privileges", "--memory", memory,
                "--memory-swap", memory, "--cpus", cpus, "--pids-limit", str(pids),
                "--ulimit", "fsize=16777216:16777216", "--ulimit", "nofile=256:256",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m,mode=1777"]

    def remove(self, name):
        limit, code, _, err = self.invoke(["rm", "-f", name], timeout=15)
        if limit or (code and "No such container" not in err):
            raise RuntimeError(f"Docker cleanup of {name} failed ({limit or code}): {err}")
