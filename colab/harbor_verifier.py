"""Harbor verifier entrypoint; trusted parent scores an unprivileged worker."""

import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time

from verdict import evaluate_response

TESTS = Path(__file__).resolve().parent
LOGS = Path("/logs/verifier")


def check():
    # The separate container receives only the selected source artifact.
    if os.geteuid() != 0 or stat.S_IMODE(TESTS.stat().st_mode) != 0o700:
        raise RuntimeError("verifier must protect its tests and run the worker as a different UID")
    source = Path("/work/solution.py")
    metadata = source.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 65536:
        raise ValueError("submission must be a regular Python file at most 64 KiB")
    source_text = source.read_text(encoding="utf-8")
    spec = json.loads((TESTS / "cases.json").read_text())
    request = {"function": spec["function"], "inputs": [case["args"] for case in spec["cases"]]}
    worker = (TESTS / "worker.py").read_text()
    started = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="oca-verifier-") as directory, tempfile.TemporaryFile() as stdout:
        work = Path(directory)
        work.chmod(0o755)
        staged = work / "solution.py"
        staged.write_text(source_text)
        staged.chmod(0o444)
        cmd = worker.replace('"/submission/solution.py"', repr(str(staged)), 1)
        # Bound the child output before it can fill its temporary file.
        cmd = "import resource; resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))\n" + cmd
        with subprocess.Popen([sys.executable, "-I", "-B", "-u", "-c", cmd], cwd=work,
                              env={"PATH": "/usr/local/bin:/usr/bin:/bin"}, stdin=subprocess.PIPE,
                              stdout=stdout, stderr=subprocess.DEVNULL, start_new_session=True,
                              user=65534, group=65534, extra_groups=[]) as child:
            try:
                child.communicate(json.dumps(request, allow_nan=False).encode(), timeout=TIMEOUT_SECONDS)
            finally:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if child.returncode:
                raise RuntimeError(f"verifier worker exited with {child.returncode}")
        stdout.seek(0)
        return evaluate_response(spec["cases"], stdout.read().decode(), "", started)


TIMEOUT_SECONDS = 6
if __name__ == "__main__":
    LOGS.mkdir(parents=True, mode=0o700, exist_ok=True)
    LOGS.chmod(0o700)
    try:
        result = check()
    except subprocess.TimeoutExpired:
        result = {"status": "test_timeout"}
    except (OSError, ValueError, RuntimeError) as exc:
        result = {"status": "test_error", "detail": str(exc)}
    (LOGS / "oca-grade.json").write_text(json.dumps(result) + "\n")
    if result["status"] not in ("pass", "fail"):
        sys.exit(2)
    (LOGS / "reward.json").write_text(json.dumps({"correctness": int(result["status"] == "pass")}) + "\n")
