"""Zero-Docker loader & grader for official `SWE-bench/SWE-bench_Verified` (Pure-Python Subset).

Targets pure-Python repositories from official SWE-bench Verified (`sympy/sympy`, `django/django`,
`pytest-dev/pytest`, `psf/requests`, `pallets/flask`) running in cached per-repo `uv venv`s with
zero Docker daemon required:
- Visible workspace (`tasks/<instance_id>/`): repo at `base_commit` + `TASK.md` containing ONLY
  the official `problem_statement` (zero file-path or test-name leakage).
- Hidden grader (`grader/<instance_id>/`): `swe_spec.json` (`FAIL_TO_PASS`, `PASS_TO_PASS`, runner)
  + `test_patch.diff` + `gold_patch.diff`.
- Hard verification gate before admission:
    * `base_commit` MUST fail `FAIL_TO_PASS` and pass `PASS_TO_PASS` (or clean fail without import crash)
    * `base_commit + gold_patch` MUST pass 100% of `FAIL_TO_PASS` + `PASS_TO_PASS`.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

from .. import ROOT
from ..grade import _limits, _parse_pytest_counts, _safe_copy_tree

# All 12 official SWE-bench Verified repos (used by SWE-smith loader to guarantee 0% repo leakage)
SWE_VERIFIED_ALL_REPOS = frozenset({
    "astropy/astropy",
    "django/django",
    "matplotlib/matplotlib",
    "mwaskom/seaborn",
    "pallets/flask",
    "psf/requests",
    "pydata/xarray",
    "pylint-dev/pylint",
    "pytest-dev/pytest",
    "scikit-learn/scikit-learn",
    "sphinx-doc/sphinx",
    "sympy/sympy",
})

# Lightweight pure-Python repos runnable in cached `uv venv`s without C compilers or Docker
PURE_PYTHON_SPECS = {
    "sympy/sympy": {
        "slug": "sympy",
        "runner": "pytest",
        "deps": ["pytest>=7,<9", "mpmath>=1.3"],
        "target_count": 22,
    },
    "django/django": {
        "slug": "django",
        "runner": "django_runtests",
        "deps": ["asgiref>=3.6", "sqlparse>=0.4", "pytz", "tblib", "pytest"],
        "target_count": 36,
    },
    "psf/requests": {
        "slug": "requests",
        "runner": "pytest",
        "deps": ["pytest", "urllib3<2", "charset-normalizer", "idna", "certifi"],
        "target_count": 5,
    },
}

_DJANGO_OK_RE = re.compile(r"Ran\s+(\d+)\s+tests?\s+in\s+", re.IGNORECASE)
_DJANGO_FAIL_RE = re.compile(r"FAILED\s*\(([^)]+)\)", re.IGNORECASE)


def parse_swe_test_list(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if str(x).strip()]
        except ValueError:
            pass
    return []


def extract_django_test_labels(test_names: list[str], test_patch: str) -> list[str]:
    """Convert SWE-bench Django `test_method (app.tests.Class)` or diff file paths to `runtests.py` labels."""
    labels: list[str] = []
    seen = set()
    # Extract modified test module paths from `test_patch` (most reliable for Django runtests.py)
    for m in re.finditer(r"^\+\+\+\s+b/tests/(.+?)\.py$", test_patch or "", re.MULTILINE):
        mod = m.group(1).replace("/", ".")
        if mod.endswith(".__init__"):
            mod = mod[:-9]
        if mod and mod not in seen:
            seen.add(mod)
            labels.append(mod)
    if labels:
        return labels
    for tn in test_names:
        m = re.search(r"\(([^)]+)\)", tn)
        if m:
            mod = m.group(1).rsplit(".", 1)[0]
            if mod and mod not in seen:
                seen.add(mod)
                labels.append(mod)
    return labels


def parse_django_runtests_output(output: str, returncode: int) -> tuple[int, int, int]:
    """Return (passed, failed, errors) from Django's `tests/runtests.py` stderr/stdout."""
    m_ran = _DJANGO_OK_RE.search(output)
    ran = int(m_ran.group(1)) if m_ran else 0
    failed = errors = 0
    m_fail = _DJANGO_FAIL_RE.search(output)
    if m_fail:
        detail = m_fail.group(1)
        mf = re.search(r"failures=(\d+)", detail)
        me = re.search(r"errors=(\d+)", detail)
        failed = int(mf.group(1)) if mf else 0
        errors = int(me.group(1)) if me else 0
    if returncode == 0 and ran > 0 and failed == 0 and errors == 0:
        return ran, 0, 0
    passed = max(0, ran - failed - errors)
    return passed, failed, errors


def ensure_repo_venv(venv_root: Path, slug: str, deps: list[str], py_version: str = "3.11") -> Path:
    """Create or reuse a cached Python 3.11 `uv venv` with pure-Python test dependencies for `slug`."""
    vdir = venv_root / f"{slug}_py{py_version.replace('.', '')}"
    py = vdir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    marker = vdir / ".oca_venv_ready_v2"
    if py.is_file() and marker.is_file():
        return vdir
    vdir.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv")
    if uv:
        # Install standalone CPython under world-readable venv_root/_uv_python (NOT /root/ 0700!)
        # so unprivileged `nobody` (grader) and `agent` (harness) UIDs can execute the venv symlink!
        uv_py_dir = venv_root / "_uv_python"
        uv_py_dir.mkdir(parents=True, exist_ok=True)
        uv_env = {**os.environ, "UV_PYTHON_INSTALL_DIR": str(uv_py_dir)}
        subprocess.run([uv, "venv", "--clear", "--python", py_version, str(vdir)],
                       check=True, timeout=120, env=uv_env)
        subprocess.run([uv, "pip", "install", "--python", str(py), "-q", *deps],
                       check=True, timeout=600, env=uv_env)
        if os.name != "nt":
            subprocess.run(["chmod", "-R", "a+rX", str(uv_py_dir), str(vdir)], check=False)
    else:
        subprocess.run([sys.executable, "-m", "venv", str(vdir)], check=True, timeout=120)
        subprocess.run([str(py), "-m", "pip", "install", "-q", *deps], check=True, timeout=600)
        if os.name != "nt":
            subprocess.run(["chmod", "-R", "a+rX", str(vdir)], check=False)
    marker.write_text("ok\n", encoding="utf-8")
    return vdir


def ensure_git_mirror(clone_root: Path, repo: str) -> Path:
    dst = clone_root / repo.replace("/", "__")
    if (dst / ".git").is_dir():
        return dst
    clone_root.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{repo}.git"
    subprocess.run(
        ["git", "-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=15",
         "clone", "--no-tags", url, str(dst)],
        check=True, timeout=300,
    )
    return dst


def export_commit(mirror: Path, commit: str, dst: Path):
    dst.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(["git", "-C", str(mirror), "archive", "--format=tar", commit],
                       capture_output=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"git archive {commit} failed: {p.stderr.decode(errors='replace')[:300]}")
    with tarfile.open(fileobj=io.BytesIO(p.stdout), mode="r:") as tf:
        tf.extractall(dst, filter="data")


def apply_patch_in_dir(work_dir: Path, patch_text: str, reverse: bool = False) -> tuple[bool, str]:
    """Apply a unified diff patch strictly inside `work_dir` (never climbing into a parent `.git` repo)."""
    if not patch_text or not patch_text.strip():
        return True, ""
    work_dir = Path(work_dir).resolve()
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(work_dir.parent)}
    base_cmd = ["git", "apply", "--whitespace=nowarn"]
    if reverse:
        base_cmd.append("-R")
    p = subprocess.run(
        [*base_cmd, "-"],
        input=patch_text.encode("utf-8"), cwd=work_dir, env=env, capture_output=True, timeout=30,
    )
    if p.returncode == 0:
        return True, ""
    p2 = subprocess.run(
        [*base_cmd, "--recount", "-"],
        input=patch_text.encode("utf-8"), cwd=work_dir, env=env, capture_output=True, timeout=30,
    )
    return (p2.returncode == 0), p2.stderr.decode(errors="replace")[-600:]


def extract_patch_py_files(patch_text: str) -> list[str]:
    """Extract unique `.py` file paths touched by a unified diff (`+++ b/...`)."""
    files: list[str] = []
    seen = set()
    for m in re.finditer(r"^\+\+\+\s+b/(.+?\.py)$", patch_text or "", re.MULTILINE):
        p = m.group(1).strip()
        if p and p not in seen:
            seen.add(p)
            files.append(p)
    return files


def grade_swe_dir(
    grader_dir: Path,
    work_dir: Path,
    timeout: int = 90,
    venv_dir: str | Path | None = None,
    apply_gold: bool = False,
) -> dict:
    """Grade a SWE-bench / SWE-smith workspace against official `test_patch.diff` (or clean tests) + F2P/P2P."""
    started = time.monotonic()
    grader_dir, work_dir = Path(grader_dir), Path(work_dir)
    spec_file = grader_dir / "swe_spec.json"
    if not spec_file.is_file():
        return {"status": "test_error", "detail": "missing swe_spec.json",
                "passed": 0, "total": 0, "wall_seconds": round(time.monotonic() - started, 3)}
    spec = json.loads(spec_file.read_text(encoding="utf-8"))
    test_patch = (grader_dir / "test_patch.diff").read_text(encoding="utf-8") if (grader_dir / "test_patch.diff").is_file() else ""
    gold_patch = (grader_dir / "gold_patch.diff").read_text(encoding="utf-8") if (grader_dir / "gold_patch.diff").is_file() else ""
    f2p = spec.get("fail_to_pass") or []
    p2p = spec.get("pass_to_pass") or []
    runner = spec.get("runner", "pytest")
    use_venv = venv_dir or spec.get("venv_dir") or ""
    reverse_gold = bool(spec.get("reverse_gold_patch", False))

    with tempfile.TemporaryDirectory(prefix="oca-swe-grade-") as tmp:
        tmp_p = Path(tmp)
        _safe_copy_tree(work_dir, tmp_p)
        # Restore unmodified test files if stored (for SWE-smith where tests live inside repo)
        clean_tests = grader_dir / "clean_tests"
        if clean_tests.is_dir():
            _safe_copy_tree(clean_tests, tmp_p)
        if apply_gold and gold_patch:
            ok_g, err_g = apply_patch_in_dir(tmp_p, gold_patch, reverse=reverse_gold)
            if not ok_g:
                return {"status": "test_error", "detail": f"gold patch failed: {err_g}",
                        "passed": 0, "total": 0, "wall_seconds": round(time.monotonic() - started, 3)}
        if test_patch:
            ok_t, err_t = apply_patch_in_dir(tmp_p, test_patch)
            if not ok_t:
                return {"status": "test_error", "detail": f"test_patch failed: {err_t}",
                        "passed": 0, "total": 0, "wall_seconds": round(time.monotonic() - started, 3)}

        if os.name != "nt":
            os.chmod(tmp_p, 0o755)
            for r, _, fs in os.walk(tmp_p):
                os.chmod(r, 0o755)
                for fn in fs:
                    os.chmod(os.path.join(r, fn), 0o644)

        py_exe = sys.executable
        if use_venv:
            cand = Path(use_venv) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if cand.is_file():
                py_exe = str(cand)

        py_paths = [str(tmp_p)]
        if (tmp_p / "src").is_dir():
            py_paths.insert(0, str(tmp_p / "src"))
        env = {
            "PYTHONPATH": os.pathsep.join(py_paths),
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(tmp_p),
        }
        if use_venv:
            env["VIRTUAL_ENV"] = str(use_venv)
        if os.name == "nt":
            for k in ("SYSTEMROOT", "TEMP", "TMP", "PATH"):
                if k in os.environ:
                    env[k] = os.environ[k]
        else:
            env["PATH"] = f"{Path(py_exe).parent}:/usr/local/bin:/usr/bin:/bin"

        if runner == "django_runtests":
            labels = spec.get("django_labels") or extract_django_test_labels(f2p + p2p, test_patch)
            if not labels:
                return {"status": "test_error", "detail": "no django test labels",
                        "passed": 0, "total": 0, "wall_seconds": round(time.monotonic() - started, 3)}
            cmd = [py_exe, "-B", "tests/runtests.py", "--verbosity=1", "--parallel=1", *labels]
        else:
            targets = list(dict.fromkeys([*f2p, *p2p[:25]]))
            if not targets:
                return {"status": "test_error", "detail": "no pytest targets",
                        "passed": 0, "total": 0, "wall_seconds": round(time.monotonic() - started, 3)}
            # Handle bare function names (e.g. sympy/sympy uses `test_issue_11617` without file path)
            has_paths = any((".py" in t or "/" in t or "::" in t) for t in targets)
            if not has_paths:
                test_files = spec.get("test_files") or extract_patch_py_files(test_patch)
                if not test_files:
                    return {"status": "test_error", "detail": "bare test names without test_files",
                            "passed": 0, "total": 0, "wall_seconds": round(time.monotonic() - started, 3)}
                k_expr = " or ".join(t.split("[", 1)[0] for t in targets[:30])
                cmd = [py_exe, "-B", "-m", "pytest", "-q", "--tb=short",
                       "-o", "cache_dir=/tmp/oca_pytest_cache_unused", "-p", "no:cacheprovider",
                       "-k", k_expr, *test_files]
            else:
                cmd = [py_exe, "-B", "-m", "pytest", "-q", "--tb=short",
                       "-o", "cache_dir=/tmp/oca_pytest_cache_unused", "-p", "no:cacheprovider", *targets]

        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=timeout, cwd=tmp_p, env=env,
                preexec_fn=None if os.name == "nt" else _limits(timeout),
            )
        except subprocess.TimeoutExpired:
            return {"status": "test_timeout", "passed": 0, "total": 0,
                    "wall_seconds": round(time.monotonic() - started, 3)}

    out = proc.stdout.decode(errors="replace")
    err = proc.stderr.decode(errors="replace")
    combined = out + "\n" + err
    if runner == "django_runtests":
        passed, failed, errors = parse_django_runtests_output(combined, proc.returncode)
        total = passed + failed + errors
    else:
        counts = _parse_pytest_counts(combined)
        passed = counts["passed"]
        failed = counts["failed"]
        errors = counts["error"]
        total = passed + failed + errors

    if proc.returncode == 0 and total > 0 and passed == total:
        status = "pass"
    elif total == 0 or (errors > 0 and passed == 0 and failed == 0):
        status = "test_error"
    else:
        status = "fail"
    return {
        "status": status,
        "wall_seconds": round(time.monotonic() - started, 3),
        "passed": passed,
        "total": total,
        "failed": failed,
        "errors": errors,
        "stdout_tail": out[-1500:],
        "stderr": err[-2000:],
    }


def grade_swe_workspace(task, work_dir: Path, timeout: int = 90) -> dict:
    return grade_swe_dir(task.grader_dir, work_dir, timeout=timeout, venv_dir=getattr(task, "venv_dir", ""))


def format_swe_task_md(repo: str, instance_id: str, problem_statement: str, runner: str) -> str:
    hint = (
        "Run `python tests/runtests.py <app_label>` to verify your fix."
        if runner == "django_runtests"
        else "Run `pytest <test_path>` to verify your fix."
    )
    return (
        f"# Issue: `{instance_id}` (`{repo}`)\n\n"
        f"## Problem Statement\n\n"
        f"{problem_statement.strip()}\n\n"
        f"## Verification Hint\n"
        f"Locate the root cause in the repository source files, apply a minimal clean fix, and avoid regressions. "
        f"{hint}\n"
    )


def build_swe_verified_subset(
    out_dir: Path,
    venv_root: Path,
    clone_root: Path,
    max_total: int = 60,
    freeze_protocol: Path | None = None,
) -> dict:
    from datasets import load_dataset

    ds = load_dataset("SWE-bench/SWE-bench_Verified", split="test")
    by_repo: dict[str, list[dict]] = {r: [] for r in PURE_PYTHON_SPECS}
    for row in ds:
        r = row["repo"]
        if r in by_repo:
            by_repo[r].append(dict(row))

    out_dir.mkdir(parents=True, exist_ok=True)
    accepted: list[dict] = []

    for repo, spec in PURE_PYTHON_SPECS.items():
        if len(accepted) >= max_total:
            break
        want = min(spec["target_count"], max_total - len(accepted))
        # Prefer newer issues first (best Python 3.11 compatibility & modern APIs)
        candidates = sorted(by_repo[repo], key=lambda x: x["instance_id"], reverse=True)
        if not candidates:
            continue
        print(f"[swe_verified] setting up {repo} (want {want} from {len(candidates)} candidates)...", flush=True)
        vdir = ensure_repo_venv(venv_root, spec["slug"], spec["deps"])
        mirror = ensure_git_mirror(clone_root, repo)

        got = 0
        for row in candidates:
            if got >= want:
                break
            iid = row["instance_id"]
            tdir = out_dir / "tasks" / iid
            gdir = out_dir / "grader" / iid
            f2p = parse_swe_test_list(row.get("FAIL_TO_PASS"))
            p2p = parse_swe_test_list(row.get("PASS_TO_PASS"))
            if not f2p:
                continue

            if not (tdir / "TASK.md").is_file() or not (gdir / "swe_spec.json").is_file():
                shutil.rmtree(tdir, ignore_errors=True)
                shutil.rmtree(gdir, ignore_errors=True)
                try:
                    export_commit(mirror, row["base_commit"], tdir)
                except Exception as e:
                    print(f"  [skip {iid}] archive err: {e}", flush=True)
                    continue
                (tdir / "TASK.md").write_text(
                    format_swe_task_md(repo, iid, row["problem_statement"], spec["runner"]), encoding="utf-8"
                )
                gdir.mkdir(parents=True, exist_ok=True)
                (gdir / "test_patch.diff").write_text(row.get("test_patch") or "", encoding="utf-8")
                (gdir / "gold_patch.diff").write_text(row.get("patch") or "", encoding="utf-8")
                swe_spec = {
                    "instance_id": iid,
                    "repo": repo,
                    "base_commit": row["base_commit"],
                    "runner": spec["runner"],
                    "venv_dir": str(vdir),
                    "fail_to_pass": f2p,
                    "pass_to_pass": p2p,
                    "django_labels": extract_django_test_labels(f2p + p2p, row.get("test_patch") or "")
                    if spec["runner"] == "django_runtests" else [],
                }
                (gdir / "swe_spec.json").write_text(json.dumps(swe_spec, indent=2) + "\n", encoding="utf-8")

            # Refresh venv_dir in swe_spec.json when upgrading Python version on cached dirs
            spec_p = gdir / "swe_spec.json"
            if spec_p.is_file():
                sdoc = json.loads(spec_p.read_text(encoding="utf-8"))
                if sdoc.get("venv_dir") != str(vdir):
                    sdoc["venv_dir"] = str(vdir)
                    spec_p.write_text(json.dumps(sdoc, indent=2) + "\n", encoding="utf-8")

            # Hard verification gate: base MUST fail, gold MUST pass 100%
            res_base = grade_swe_dir(gdir, tdir, timeout=90, venv_dir=vdir, apply_gold=False)
            if res_base["status"] != "fail":
                shutil.rmtree(tdir, ignore_errors=True)
                shutil.rmtree(gdir, ignore_errors=True)
                continue
            res_gold = grade_swe_dir(gdir, tdir, timeout=90, venv_dir=vdir, apply_gold=True)
            if res_gold["status"] != "pass":
                shutil.rmtree(tdir, ignore_errors=True)
                shutil.rmtree(gdir, ignore_errors=True)
                continue

            got += 1
            accepted.append({
                "id": iid,
                "split": "swe_verified",
                "kind": "swe_verified",
                "domain": f"swe_{spec['slug']}",
                "repo": repo,
                "base_commit": row["base_commit"],
                "venv_dir": str(vdir),
                "passed": {
                    "base": f"{res_base['passed']}/{res_base['total']}",
                    "gold": f"{res_gold['passed']}/{res_gold['total']}",
                },
            })
            print(f"  [OK {got}/{want}] {iid}: base={res_base['passed']}/{res_base['total']} -> gold={res_gold['passed']}/{res_gold['total']}", flush=True)

    accepted.sort(key=lambda r: r["id"])
    (out_dir / "manifest.json").write_text(json.dumps({"tasks": accepted}, indent=2) + "\n", encoding="utf-8")
    summary = {
        "benchmark": "SWE-bench/SWE-bench_Verified (Pure-Python Zero-Docker Verified Subset)",
        "n_verified": len(accepted),
        "by_repo": {r: sum(1 for a in accepted if a["repo"] == r) for r in PURE_PYTHON_SPECS},
        "instance_ids": [a["id"] for a in accepted],
    }
    if freeze_protocol:
        freeze_protocol.parent.mkdir(parents=True, exist_ok=True)
        freeze_protocol.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("\n=== SWE-BENCH VERIFIED PURE-PYTHON SUBSET READY ===", flush=True)
    print(json.dumps({k: v for k, v in summary.items() if k != "instance_ids"}, indent=2), flush=True)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data" / "swe_verified_v1")
    ap.add_argument("--venv-root", type=Path, default=Path("/content/swe_venvs"))
    ap.add_argument("--clone-root", type=Path, default=Path("/content/swe_mirrors"))
    ap.add_argument("--max-total", type=int, default=60)
    ap.add_argument("--freeze-protocol", type=Path, default=ROOT / "protocol" / "swe_verified_60.json")
    args = ap.parse_args()
    build_swe_verified_subset(args.out_dir, args.venv_root, args.clone_root, args.max_total, args.freeze_protocol)


if __name__ == "__main__":
    main()
