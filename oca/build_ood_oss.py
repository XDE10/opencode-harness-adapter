"""Build an out-of-distribution (OOD) heldout benchmark from real pure-Python OSS bugfix commits.

Mines lightweight, zero-C-dependency open-source Python repositories (e.g. `pypa/packaging`,
`hukkin/tomli`, `more-itertools/more-itertools`, `pallets/click`) for real historical bugfix commits
that touch 1-3 source `.py` files and >=1 pytest test file.

For each candidate commit `C`:
  - Visible workspace (`tasks/<id>/`): source code at `C~1` (buggy) + lightweight visible smoke tests
    (excluding the newly modified regression test file so the agent cannot see the hidden test).
  - Hidden grader (`grader/<id>/`):
      * `tests_hidden/`: the regression test file(s) from commit `C`
      * `reference/`: source code at commit `C` (fixed)
  - Hard pytest verification gate via `oca.grade.grade_repo`:
      * `original` (`C~1`) MUST fail (`status == "fail"`, `passed < total`, NOT broken import/collection)
      * `reference` (`C`) MUST pass 100% (`status == "pass"`, `passed == total >= 3`)
  - Every task is assigned `split="heldout"` (strictly OOD evaluation only) with full commit provenance.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from . import ROOT
from .grade import grade_repo

CLONE_CACHE = ROOT / ".cache" / "oss_clones"

OSS_REPOS = [
    {
        "slug": "packaging",
        "url": "https://github.com/pypa/packaging.git",
        "license": "Apache-2.0 OR BSD-2-Clause",
        "src_root": "src",
        "test_root": "tests",
        "max_tasks": 6,
    },
    {
        "slug": "tomli",
        "url": "https://github.com/hukkin/tomli.git",
        "license": "MIT",
        "src_root": "src",
        "test_root": "tests",
        "max_tasks": 5,
    },
    {
        "slug": "click",
        "url": "https://github.com/pallets/click.git",
        "license": "BSD-3-Clause",
        "src_root": "src",
        "test_root": "tests",
        "max_tasks": 5,
    },
    {
        "slug": "more_itertools",
        "url": "https://github.com/more-itertools/more-itertools.git",
        "license": "MIT",
        "src_root": "more_itertools",
        "test_root": "tests",
        "max_tasks": 6,
    },
]


def _git(repo: Path, *args: str, timeout: int = 30) -> str:
    env = os.environ.copy()
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env,
    )
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr[:300]}")
    return p.stdout


def ensure_clone(spec: dict, depth: int = 350) -> Path:
    CLONE_CACHE.mkdir(parents=True, exist_ok=True)
    dst = CLONE_CACHE / spec["slug"]
    if (dst / ".git").is_dir():
        return dst
    print(f"[ood] cloning {spec['url']} (depth={depth})...", flush=True)
    p = subprocess.run(
        ["git", "-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=12",
         "clone", "--depth", str(depth), "--no-tags", spec["url"], str(dst)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
    )
    if p.returncode != 0:
        raise RuntimeError(f"clone failed for {spec['slug']}: {p.stderr[:300]}")
    return dst


def export_commit_tree(repo: Path, commit: str, dst: Path):
    dst.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", commit],
        capture_output=True, timeout=30,
    )
    if p.returncode != 0:
        raise RuntimeError(f"git archive {commit} failed")
    import io, tarfile
    with tarfile.open(fileobj=io.BytesIO(p.stdout), mode="r:") as tf:
        tf.extractall(dst, filter="data")


def _prune_tree(root: Path, src_root: str, test_root: str, keep_tests: list[str] | None = None):
    """Keep only source package, minimal pytest config, and selected tests so task dirs stay lean."""
    keep_top = {src_root.split("/")[0], "pyproject.toml", "setup.cfg"}
    if keep_tests:
        keep_top.add(test_root.split("/")[0])
    for child in list(root.iterdir()):
        if child.name not in keep_top:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
    tdir = root / test_root
    if tdir.is_dir() and keep_tests is not None:
        keep_set = {Path(k).as_posix() for k in keep_tests}
        for fp in list(tdir.rglob("*")):
            if fp.is_file():
                rel = fp.relative_to(root).as_posix()
                if rel not in keep_set and fp.name != "conftest.py" and fp.name != "__init__.py":
                    fp.unlink(missing_ok=True)


def _format_task_md(spec: dict, sha: str, subject: str, body: str, src_files: list[str],
                    fail_summary: str) -> str:
    clean_body = re.sub(r"(?im)^(signed-off-by|co-authored-by|reviewed-by):.*$", "", body or "").strip()
    clean_body = clean_body[:900]
    src_bullets = "\n".join(f"- `{f}`" for f in src_files)
    return (
        f"# Issue in `{spec['slug']}`: {subject}\n\n"
        f"This repository snapshot comes from `{spec['slug']}` (license: {spec['license']}).\n\n"
        f"## Problem Summary\n"
        f"{subject}\n\n"
        + (f"{clean_body}\n\n" if clean_body else "")
        + f"## Scope\n"
        f"Investigate and fix the bug in the library source modules (relevant area includes:\n{src_bullets}\n).\n"
        f"Run `pytest` to verify your changes and avoid regressions.\n\n"
        f"## Observed Failure Signal (excerpt)\n"
        f"```text\n{fail_summary[:700]}\n```\n"
    )


def mine_repo(spec: dict, out_base: Path, target: int) -> list[dict]:
    repo = ensure_clone(spec)
    log_out = _git(repo, "log", "--no-merges", "--format=%H%x1f%s%x1f%b%x1e", "-n", "260")
    entries = [e.strip() for e in log_out.split("\x1e") if e.strip()]
    accepted = []
    seen_files = set()

    for entry in entries:
        if len(accepted) >= target:
            break
        parts = entry.split("\x1f")
        if len(parts) < 2:
            continue
        sha, subject = parts[0].strip(), parts[1].strip()
        body = parts[2].strip() if len(parts) > 2 else ""

        # Skip pure docs/typing/release/chore commits
        if re.search(r"\b(bump|release|changelog|typing|mypy|ruff|flake8|lint|docs?|ci|workflow|pre-commit|copyright)\b",
                     subject, re.IGNORECASE):
            continue

        try:
            parent = _git(repo, "rev-parse", f"{sha}^").strip()
            numstat = _git(repo, "diff", "--numstat", parent, sha)
        except Exception:
            continue

        src_files, test_files = [], []
        total_churn = 0
        ok_files = True
        for ln in numstat.splitlines():
            cols = ln.split("\t")
            if len(cols) != 3:
                continue
            add_s, del_s, path_s = cols
            if add_s == "-" or del_s == "-":
                ok_files = False
                break
            churn = int(add_s) + int(del_s)
            if path_s.startswith(spec["src_root"] + "/") and path_s.endswith(".py"):
                src_files.append(path_s)
                total_churn += churn
            elif path_s.startswith(spec["test_root"] + "/") and path_s.endswith(".py") and "test_" in Path(path_s).name:
                test_files.append(path_s)

        if not ok_files or not (1 <= len(src_files) <= 3) or not (1 <= len(test_files) <= 2):
            continue
        if not (2 <= total_churn <= 80):
            continue

        # Diversify across commits touching different files/tests
        sig = (tuple(sorted(src_files)), test_files[0])
        if seen_files and list(seen_files).count(sig) >= 2:
            continue

        slug = re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")[:32].strip("-")
        tid = f"ood-{spec['slug']}-{sha[:7]}-{slug or 'fix'}"
        tdir = out_base / "tasks" / tid
        gdir = out_base / "grader" / tid

        if (tdir / "TASK.md").is_file() and (gdir / "tests_hidden").is_dir():
            res_orig = grade_repo(gdir, tdir, timeout=20)
            res_ref = grade_repo(gdir, gdir / "reference", timeout=20)
            if res_orig["status"] == "fail" and res_ref["status"] == "pass":
                accepted.append({
                    "id": tid, "split": "heldout", "domain": f"oss_{spec['slug']}",
                    "kind": "repo_pytest", "source_repo": spec["url"], "commit": sha,
                    "license": spec["license"],
                    "passed": {"original": f"{res_orig['passed']}/{res_orig['total']}",
                               "reference": f"{res_ref['passed']}/{res_ref['total']}"},
                })
                seen_files.add(sig)
                print(f"[ood:{spec['slug']}] cached {tid}", flush=True)
                continue

        with tempfile.TemporaryDirectory(prefix="oca-ood-mine-") as tmp:
            tmp_p = Path(tmp)
            buggy = tmp_p / "buggy"
            fixed = tmp_p / "fixed"
            export_commit_tree(repo, parent, buggy)
            export_commit_tree(repo, sha, fixed)

            # Build hidden tests dir with modified regression test(s) + conftest if present
            hidden_dir = tmp_p / "grader" / "tests_hidden"
            hidden_dir.mkdir(parents=True, exist_ok=True)
            for tf in test_files:
                fp = fixed / tf
                if fp.is_file():
                    shutil.copy2(fp, hidden_dir / fp.name)
            conftest = fixed / spec["test_root"] / "conftest.py"
            if conftest.is_file():
                shutil.copy2(conftest, hidden_dir / "conftest.py")

            # Pick 1 unrelated visible smoke test file from buggy tree (if available)
            vis_smoke = []
            buggy_test_dir = buggy / spec["test_root"]
            if buggy_test_dir.is_dir():
                for cand in sorted(buggy_test_dir.glob("test_*.py")):
                    rel = cand.relative_to(buggy).as_posix()
                    if rel not in test_files and cand.stat().st_size < 25_000:
                        vis_smoke.append(rel)
                        break

            _prune_tree(buggy, spec["src_root"], spec["test_root"], keep_tests=vis_smoke)
            _prune_tree(fixed, spec["src_root"], spec["test_root"], keep_tests=vis_smoke)

            # Verify reference passes 100% AND buggy fails cleanly (not collection/import error!)
            res_ref = grade_repo(tmp_p / "grader", fixed, timeout=25)
            if res_ref["status"] != "pass" or res_ref.get("total", 0) < 3:
                continue
            res_orig = grade_repo(tmp_p / "grader", buggy, timeout=25)
            if res_orig["status"] != "fail" or res_orig.get("errors", 0) > 0:
                continue
            if res_orig.get("passed", 0) >= res_ref.get("total", 0):
                continue

            # Extract concise failure lines (without leaking the hidden test source)
            fail_lines = [
                ln for ln in (res_orig.get("stdout_tail") or "").splitlines()
                if ln.startswith(("FAILED ", "E   "))
            ][:8]
            fail_excerpt = "\n".join(fail_lines) or f"{res_orig['passed']}/{res_orig['total']} hidden tests pass before fix."

            shutil.rmtree(tdir, ignore_errors=True)
            shutil.rmtree(gdir, ignore_errors=True)
            shutil.copytree(buggy, tdir)
            shutil.copytree(fixed, gdir / "reference")
            shutil.copytree(hidden_dir, gdir / "tests_hidden")
            (tdir / "TASK.md").write_text(
                _format_task_md(spec, sha, subject, body, src_files, fail_excerpt), encoding="utf-8"
            )
            shutil.copy2(tdir / "TASK.md", gdir / "reference" / "TASK.md")

            row = {
                "id": tid, "split": "heldout", "domain": f"oss_{spec['slug']}",
                "kind": "repo_pytest", "source_repo": spec["url"], "commit": sha,
                "license": spec["license"],
                "src_files": src_files,
                "passed": {
                    "original": f"{res_orig['passed']}/{res_orig['total']}",
                    "reference": f"{res_ref['passed']}/{res_ref['total']}",
                },
            }
            accepted.append(row)
            seen_files.add(sig)
            print(f"[ood:{spec['slug']}] OK {tid} ({row['passed']}) churn={total_churn}", flush=True)

    return accepted


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data" / "ood_oss")
    ap.add_argument("--max-total", type=int, default=18)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for spec in OSS_REPOS:
        if len(all_rows) >= args.max_total:
            break
        want = min(spec["max_tasks"], args.max_total - len(all_rows))
        try:
            all_rows.extend(mine_repo(spec, args.out_dir, target=want))
        except Exception as e:
            print(f"[ood:{spec['slug']}] skipped due to error: {e}", flush=True)

    all_rows.sort(key=lambda r: r["id"])
    (args.out_dir / "manifest.json").write_text(json.dumps({"tasks": all_rows}, indent=2) + "\n", encoding="utf-8")
    summary = {
        "total_ood_heldout": len(all_rows),
        "repos": sorted({r["domain"] for r in all_rows}),
        "tasks": [{"id": r["id"], "commit": r["commit"][:8], "passed": r["passed"]} for r in all_rows],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("\n=== OOD OSS EXTRACTION COMPLETE ===", flush=True)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
