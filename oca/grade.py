"""Hidden-test grading in a resource-limited subprocess (single_file + multi-file repo_pytest).

No Docker daemon required:
- For `single_file`: runs an isolated Python worker receiving only inputs; expected outputs stay in parent.
- For `repo_pytest`: copies the submitted workspace + hidden pytest suite into a fresh temp dir and executes
  `pytest -q` as unprivileged `nobody` (on Linux/Colab) with CPU/RAM/FSIZE/NPROC rlimits.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

MAX_SOURCE = 64 * 1024
WORKER = r'''
import contextlib, json, runpy, sys
def decode(v):
    if isinstance(v, list): return [decode(i) for i in v]
    if isinstance(v, dict):
        if set(v) == {"$float"}: return float(v["$float"])
        return {k: decode(i) for k, i in v.items()}
    return v
req = json.load(sys.stdin)
out = []
with contextlib.redirect_stdout(sys.stderr):
    fn = runpy.run_path(sys.argv[1])[req["function"]]
    for args in req["inputs"]:
        try: out.append({"value": fn(*decode(args))})
        except Exception as e: out.append({"raises": type(e).__name__})
print(json.dumps(out, ensure_ascii=True, allow_nan=False))
'''

_PYTEST_SUMMARY_RE = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed)")


def _limits(cpu_seconds: int):
    def apply():
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 << 20, 16 << 20))
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except (ValueError, OSError):
            pass
        os.setsid()
        if os.geteuid() == 0:
            os.setgid(65534)
            os.setuid(65534)
    return apply


def _result(status, started, **extra):
    return {"status": status, "wall_seconds": round(time.monotonic() - started, 3), **extra}


def grade_source(grader_dir: Path, source: str, timeout=10):
    started = time.monotonic()
    spec = json.loads((Path(grader_dir) / "cases.json").read_text(encoding="utf-8"))
    cases = spec["cases"]
    if len(source.encode()) > MAX_SOURCE:
        return _result("test_error", started, detail="submission too large", passed=0, total=len(cases))
    request = json.dumps({"function": spec["function"], "inputs": [c["args"] for c in cases]}).encode()
    with tempfile.TemporaryDirectory(prefix="oca-grade-") as tmp:
        if os.name != "nt":
            os.chmod(tmp, 0o755)
        path = Path(tmp) / "solution.py"
        path.write_text(source, encoding="utf-8")
        if os.name != "nt":
            path.chmod(0o444)
        env = {"SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows")} if os.name == "nt" else {"PATH": "/usr/bin:/bin"}
        try:
            proc = subprocess.run([sys.executable, "-I", "-B", "-c", WORKER, str(path)], input=request,
                                  capture_output=True, timeout=timeout, cwd=tmp, env=env,
                                  preexec_fn=None if os.name == "nt" else _limits(timeout))
        except subprocess.TimeoutExpired:
            return _result("test_timeout", started, passed=0, total=len(cases))
    out, err = proc.stdout.decode(errors="replace"), proc.stderr.decode(errors="replace")[-2000:]
    if proc.returncode:
        return _result("test_error", started, detail=f"exit {proc.returncode}", stderr=err, passed=0, total=len(cases))
    try:
        observed = json.loads(out)
        assert isinstance(observed, list) and len(observed) == len(cases)
    except (ValueError, AssertionError):
        return _result("test_error", started, detail="bad worker output", stderr=err, passed=0, total=len(cases))
    outcomes = []
    for case, actual in zip(cases, observed):
        expected = {k: case[k] for k in ("raises", "value") if k in case}
        ok = json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)
        outcomes.append({"id": case["id"], "status": "pass" if ok else "fail"})
    passed = sum(o["status"] == "pass" for o in outcomes)
    status = "pass" if passed == len(cases) else "fail"
    return _result(status, started, passed=passed, total=len(cases), cases=outcomes)


def grade_file(grader_dir: Path, solution: Path, timeout=10):
    solution = Path(solution)
    if solution.is_symlink() or not solution.is_file():
        return {"status": "test_error", "detail": "solution.py missing or not a regular file", "passed": 0, "total": 0}
    return grade_source(grader_dir, solution.read_text(encoding="utf-8", errors="replace"), timeout)


def _safe_copy_tree(src: Path, dst: Path):
    """Copy a workspace tree while rejecting symlinks and skipping caches."""
    src = Path(src)
    dst = Path(dst)
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache", ".git", ".venv")]
        rel = Path(root).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for f in files:
            sp = Path(root) / f
            if sp.is_symlink():
                continue
            shutil.copy2(sp, dst / rel / f)


def _parse_pytest_counts(output: str) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    for ln in reversed(lines[-8:]):
        hits = _PYTEST_SUMMARY_RE.findall(ln)
        if hits:
            for num_s, label in hits:
                key = "error" if label.startswith("error") else ("passed" if label == "passed" else ("failed" if label == "failed" else "skipped"))
                counts[key] += int(num_s)
            break
    return counts


def grade_repo(grader_dir: Path, work_dir: Path, timeout: int = 15, tests_subdir: str = "tests_hidden"):
    """Run hidden pytest suite against a multi-file Python repository in an isolated temp directory."""
    started = time.monotonic()
    grader_dir, work_dir = Path(grader_dir), Path(work_dir)
    hidden_src = grader_dir / tests_subdir
    if not hidden_src.is_dir():
        return _result("test_error", started, detail=f"missing {tests_subdir}", passed=0, total=0)
    if not work_dir.is_dir():
        return _result("test_error", started, detail="missing work_dir", passed=0, total=0)

    with tempfile.TemporaryDirectory(prefix="oca-repo-grade-") as tmp:
        tmp_p = Path(tmp)
        _safe_copy_tree(work_dir, tmp_p)
        hidden_dst = tmp_p / "_oca_hidden_tests"
        shutil.copytree(hidden_src, hidden_dst)
        if os.name != "nt":
            os.chmod(tmp_p, 0o755)
            for r, ds, fs in os.walk(tmp_p):
                os.chmod(r, 0o755)
                for fn in fs:
                    os.chmod(os.path.join(r, fn), 0o644)

        py_paths = [str(tmp_p)]
        if (tmp_p / "src").is_dir():
            py_paths.insert(0, str(tmp_p / "src"))
        env = {
            "PYTHONPATH": os.pathsep.join(py_paths),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        if os.name == "nt":
            for k in ("SYSTEMROOT", "TEMP", "TMP", "PATH"):
                if k in os.environ:
                    env[k] = os.environ[k]
        else:
            env["PATH"] = "/usr/local/bin:/usr/bin:/bin"

        cmd = [sys.executable, "-B", "-m", "pytest", "-q", "--tb=short",
               "-o", "cache_dir=/tmp/oca_pytest_cache_unused", "-p", "no:cacheprovider",
               str(hidden_dst)]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=timeout, cwd=tmp_p, env=env,
                preexec_fn=None if os.name == "nt" else _limits(timeout),
            )
        except subprocess.TimeoutExpired:
            return _result("test_timeout", started, passed=0, total=0)

    out = proc.stdout.decode(errors="replace")
    err = proc.stderr.decode(errors="replace")[-2000:]
    counts = _parse_pytest_counts(out + "\n" + err)
    passed = counts["passed"]
    total = counts["passed"] + counts["failed"] + counts["error"]
    if proc.returncode == 0 and total > 0 and passed == total:
        status = "pass"
    elif total == 0 or counts["error"] > 0 and passed == 0 and counts["failed"] == 0:
        status = "test_error"
    else:
        status = "fail"
    return _result(status, started, passed=passed, total=total,
                   failed=counts["failed"], errors=counts["error"],
                   stdout_tail=out[-1500:], stderr=err)


def grade_task(task, work_dir: Path, timeout: int = 15):
    if getattr(task, "kind", "single_file") == "repo_pytest":
        return grade_repo(task.grader_dir, work_dir, timeout=timeout)
    return grade_file(task.grader_dir, Path(work_dir) / "solution.py", timeout=timeout)


def controls(tasks, timeout=15):
    """Verify original=fail / reference=pass / partial=fail for every task (single_file or repo_pytest)."""
    rows = []
    for t in tasks:
        row = {"task": t.id, "kind": t.kind}
        if t.kind == "repo_pytest":
            for variant, path in (("original", t.task_dir),
                                  ("reference", t.grader_dir / "reference"),
                                  ("partial", t.grader_dir / "partial")):
                row[variant] = grade_repo(t.grader_dir, path, timeout)["status"]
        else:
            for variant, path in (("original", t.task_dir / "solution.py"),
                                  ("reference", t.grader_dir / "reference.py"),
                                  ("partial", t.grader_dir / "partial.py")):
                row[variant] = grade_file(t.grader_dir, path, timeout)["status"]
        row["ok"] = (row["original"], row["reference"], row["partial"]) == ("fail", "pass", "fail")
        rows.append(row)
    return rows


if __name__ == "__main__":
    from .tasks import load
    results = controls(load())
    for r in results:
        print(f"{r['task']:32} {r['kind']:11} {r['original']:10} {r['reference']:10} {r['partial']:10} {'OK' if r['ok'] else 'BAD'}")
    print(f"{sum(r['ok'] for r in results)}/{len(results)} tasks valid")
    raise SystemExit(0 if all(r["ok"] for r in results) else 1)
