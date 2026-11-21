"""Apply trusted expectations on the host; the submission only receives inputs."""

import json
from pathlib import Path
import tempfile
import time

from containers import Docker, IMAGE, ROOT
from protocol import LIMITS
from verdict import evaluate_response, result

TIMEOUT = LIMITS["grade_wall_s"]
MAX_SOURCE = 64 * 1024


def read_submission(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SOURCE:
        raise ValueError("expected a regular solution.py of at most 64 KiB")
    with path.open(encoding="utf-8", newline="") as file:
        return file.read()


def grade(docker: Docker, task_id: str, submission: Path):
    started = time.monotonic()
    spec = json.loads((ROOT / "grader" / task_id / "cases.json").read_text())
    cases = spec["cases"]
    request = {"function": spec["function"], "inputs": [case["args"] for case in cases]}
    try:
        source = read_submission(submission)
    except (OSError, ValueError) as exc:
        return result("test_error", started, detail=str(exc))

    with tempfile.TemporaryDirectory(prefix="oca-grading-") as tmp:
        staged = Path(tmp) / "solution.py"
        staged.write_text(source, encoding="utf-8")
        staged.chmod(0o444)
        name = docker.name("grade")
        args = docker.sandbox(name) + ["-i", "--log-driver=none", "--workdir=/submission"]
        args += docker.mount(staged, "/submission/solution.py")
        worker = (ROOT / "harness" / "worker.py").read_text(encoding="utf-8")
        try:
            limit, code, out, err = docker.invoke(
                args + [IMAGE, "python", "-I", "-B", "-u", "-c", worker],
                payload=json.dumps(request, allow_nan=False).encode(), timeout=TIMEOUT,
            )
        finally:
            docker.remove(name)

    if limit == "timeout":
        return result("test_timeout", started, detail=f"exceeded {TIMEOUT}s", stderr=err)
    if limit or code:
        return result("test_error", started, detail=limit or f"exit {code}", stderr=err)
    return evaluate_response(cases, out, err, started)
