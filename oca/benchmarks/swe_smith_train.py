"""Zero-contamination multi-file RL training set builder from `SWE-bench/SWE-smith-py`.

Schema reality (verified live against Hugging Face `SWE-bench/SWE-smith-py`):
- `repo` is a public SWE-smith mirror `swesmith/<owner>__<name>.<hash>` whose `HEAD` is the clean
  GOLD repository state where `FAIL_TO_PASS` + `PASS_TO_PASS` pass.
- `patch` is the BUG-INTRODUCING mutation patch: applying `patch` to `HEAD` creates the buggy visible
  workspace (`tasks/<id>/`), and reversing `patch` (`git apply -R`) restores the gold fix.
- Strictly blacklists all 12 `SWE-bench/SWE-bench_Verified` repositories (0% repo contamination!).
- Installs each repo's lightweight pure-Python dependencies into a cached `uv venv` and verifies
  every task (`buggy` fails F2P, `gold` passes 100% F2P+P2P) before admitting into `manifest.json`.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .. import ROOT
from .swe_verified import (
    SWE_VERIFIED_ALL_REPOS,
    apply_patch_in_dir,
    export_commit,
    format_swe_task_md,
    grade_swe_dir,
    parse_swe_test_list,
)

# Proven 100%-verified lightweight pure-Python repos (0% overlap with SWE-bench Verified!)
PROVEN_SMITH_REPOS = {
    "hukkin/tomli": ["pytest"],
    "jd/tenacity": ["pytest"],
    "oauthlib/oauthlib": ["pytest", "cryptography", "pyjwt", "blinker"],
    "andialbrecht/sqlparse": ["pytest"],
    "bottlepy/bottle": ["pytest"],
    "chardet/chardet": ["pytest"],
    "google/textfsm": ["pytest", "six"],
    "keleshev/schema": ["pytest"],
    "luozhouyang/python-string-similarity": ["pytest"],
    "Knio/dominate": ["pytest"],
}

PREFERRED_SMITH_REPOS = {
    **PROVEN_SMITH_REPOS,
    "pypa/packaging": ["pytest"],
    "pallets/click": ["pytest"],
    "pallets/jinja": ["pytest", "markupsafe"],
    "pallets/itsdangerous": ["pytest"],
    "more-itertools/more-itertools": ["pytest"],
    "encode/httpx": ["pytest", "anyio", "httpcore", "certifi", "idna", "sniffio"],
    "python-attrs/attrs": ["pytest", "hypothesis"],
    "marshmallow-code/marshmallow": ["pytest"],
    "Textualize/rich": ["pytest", "markdown-it-py", "pygments"],
    "yaml/pyyaml": ["pytest"],
    "dateutil/dateutil": ["pytest", "six", "hypothesis"],
    "pyjwt/pyjwt": ["pytest", "cryptography"],
    "facelessuser/soupsieve": ["pytest"],
}

assert not (set(PREFERRED_SMITH_REPOS) & SWE_VERIFIED_ALL_REPOS), "Repo leakage with SWE-bench Verified!"


def _normalize_repo_name(raw_repo: str) -> str:
    """Convert `swesmith/owner__name.hash` -> `owner/name`."""
    s = raw_repo.strip()
    if s.startswith("swesmith/"):
        s = s[len("swesmith/"):]
    s = s.split(".", 1)[0]
    if "__" in s and "/" not in s:
        s = s.replace("__", "/", 1)
    return s


def _ensure_swesmith_mirror(clone_root: Path, raw_repo: str) -> Path:
    """Shallow-clone `https://github.com/swesmith/<slug>.git` (HEAD = clean gold state)."""
    slug = raw_repo.replace("/", "__")
    dst = clone_root / slug
    if (dst / ".git").is_dir():
        return dst
    clone_root.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{raw_repo}.git"
    subprocess.run(
        ["git", "-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=12",
         "clone", "--depth", "1", "--no-tags", url, str(dst)],
        check=True, timeout=180,
    )
    return dst


def _ensure_smith_venv(venv_root: Path, slug: str, mirror: Path, extra_deps: list[str], py_version: str = "3.11") -> Path:
    """Create cached Python 3.11 `uv venv` with ONLY third-party deps (uninstalls repo itself so workspace wins)."""
    vdir = venv_root / f"smith_{slug}_py{py_version.replace('.', '')}"
    py = vdir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    marker = vdir / ".oca_venv_ready_v2"
    if py.is_file() and marker.is_file():
        return vdir
    vdir.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv")
    pkg_guess = slug.split("_")[-1].replace("_", "-")
    if uv:
        uv_py_dir = venv_root / "_uv_python"
        uv_py_dir.mkdir(parents=True, exist_ok=True)
        uv_env = {**os.environ, "UV_PYTHON_INSTALL_DIR": str(uv_py_dir)}
        subprocess.run([uv, "venv", "--clear", "--python", py_version, str(vdir)],
                       check=True, timeout=120, env=uv_env)
        subprocess.run([uv, "pip", "install", "--python", str(py), "-q", "pytest", *extra_deps],
                       check=False, timeout=300, env=uv_env)
        # Pull transitive deps via repo metadata, then uninstall repo package itself so PYTHONPATH workspace ALWAYS wins
        rc_i = subprocess.run(
            [uv, "pip", "install", "--python", str(py), "-q", "--no-build-isolation", str(mirror)],
            capture_output=True, timeout=240, env=uv_env,
        ).returncode
        if rc_i == 0:
            subprocess.run([uv, "pip", "uninstall", "--python", str(py), "-q", pkg_guess],
                           check=False, timeout=60, env=uv_env)
            pp = mirror / "pyproject.toml"
            if pp.is_file():
                import re
                m = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)["\']', pp.read_text(encoding="utf-8", errors="replace"))
                if m and m.group(1).lower() != pkg_guess.lower():
                    subprocess.run([uv, "pip", "uninstall", "--python", str(py), "-q", m.group(1)],
                                   check=False, timeout=60, env=uv_env)
        if os.name != "nt":
            subprocess.run(["chmod", "-R", "a+rX", str(uv_py_dir), str(vdir)], check=False)
    else:
        subprocess.run([sys.executable, "-m", "venv", str(vdir)], check=True, timeout=120)
        subprocess.run([str(py), "-m", "pip", "install", "-q", "pytest", *extra_deps], check=False, timeout=300)
        if os.name != "nt":
            subprocess.run(["chmod", "-R", "a+rX", str(vdir)], check=False)
    marker.write_text("ok\n", encoding="utf-8")
    return vdir


def build_swe_smith_train(
    out_dir: Path,
    venv_root: Path,
    clone_root: Path,
    max_total: int = 160,
    max_per_repo: int = 16,
    dataset_name: str = "SWE-bench/SWE-smith-py",
) -> dict:
    from datasets import load_dataset

    print(f"[swe_smith] streaming {dataset_name} (0% overlap with {len(SWE_VERIFIED_ALL_REPOS)} SWE-bench Verified repos)...", flush=True)
    ds = load_dataset(dataset_name, split="train", streaming=True)

    # Dynamically collect candidates grouped by raw `swesmith/...` mirror repo (excluding Verified repos!)
    by_raw_repo: dict[str, list[dict]] = {}
    scanned = 0
    for row in ds:
        scanned += 1
        raw_repo = str(row.get("repo") or "").strip()
        norm_repo = _normalize_repo_name(raw_repo)
        if not raw_repo or norm_repo in SWE_VERIFIED_ALL_REPOS:
            continue
        if not (row.get("problem_statement") and row.get("patch") and row.get("FAIL_TO_PASS")):
            continue
        bucket = by_raw_repo.setdefault(raw_repo, [])
        if len(bucket) < max_per_repo * 2:
            bucket.append({**dict(row), "_norm_repo": norm_repo})
        if len(by_raw_repo) >= 35 and sum(len(v) for v in by_raw_repo.values()) >= max_total * 3:
            break
        if scanned >= 25_000:
            break

    # Prioritize proven 100%-verified repos first (saves ~5 min probing broken repos on fresh VMs)
    ordered_repos = sorted(
        by_raw_repo.keys(),
        key=lambda rr: (
            0 if _normalize_repo_name(rr) in PROVEN_SMITH_REPOS else (1 if _normalize_repo_name(rr) in PREFERRED_SMITH_REPOS else 2),
            -len(by_raw_repo[rr]),
            rr,
        ),
    )
    print(f"[swe_smith] discovered {len(ordered_repos)} non-Verified repos from {scanned} rows", flush=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    accepted: list[dict] = []

    for raw_repo in ordered_repos:
        if len(accepted) >= max_total:
            break
        norm_repo = _normalize_repo_name(raw_repo)
        cands = by_raw_repo[raw_repo]
        slug = norm_repo.replace("/", "_").replace("-", "_").lower()
        want = min(max_per_repo, max_total - len(accepted))
        print(f"[swe_smith] probing {raw_repo} ({norm_repo}, want {want}/{len(cands)})...", flush=True)
        try:
            mirror = _ensure_swesmith_mirror(clone_root, raw_repo)
            extra_deps = PREFERRED_SMITH_REPOS.get(norm_repo, [])
            vdir = _ensure_smith_venv(venv_root, slug, mirror, extra_deps)
        except Exception as e:
            print(f"  [skip {raw_repo}] setup err: {e}", flush=True)
            continue

        got = 0
        consecutive_errs = 0
        for row in cands:
            if got >= want or consecutive_errs >= 4:
                break
            raw_id = str(row.get("instance_id") or f"smith-{slug}-{got}")
            iid = f"smith-{raw_id}" if not raw_id.startswith("smith-") else raw_id
            iid = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in iid)[:72]
            tdir = out_dir / "tasks" / iid
            gdir = out_dir / "grader" / iid
            f2p = parse_swe_test_list(row.get("FAIL_TO_PASS"))
            p2p = parse_swe_test_list(row.get("PASS_TO_PASS"))
            bug_patch = str(row.get("patch") or "")
            if not f2p or not bug_patch.strip():
                continue

            if not (tdir / "TASK.md").is_file() or not (gdir / "swe_spec.json").is_file():
                shutil.rmtree(tdir, ignore_errors=True)
                shutil.rmtree(gdir, ignore_errors=True)
                try:
                    export_commit(mirror, "HEAD", tdir)
                except Exception as exc:
                    print(f"  [rej {iid}] export_commit err: {exc}", flush=True)
                    consecutive_errs += 1
                    continue

                # Snapshot clean test directories before applying bug patch so grader restores immutable tests
                clean_tests_dst = gdir / "clean_tests"
                for tname in ("tests", "test", "testing"):
                    if (tdir / tname).is_dir():
                        shutil.copytree(tdir / tname, clean_tests_dst / tname, dirs_exist_ok=True, symlinks=True)

                # Apply SWE-smith bug-introducing mutation patch to turn HEAD -> buggy workspace
                ok_bug, err_bug = apply_patch_in_dir(tdir, bug_patch)
                if not ok_bug:
                    print(f"  [rej {iid}] apply_bug err: {err_bug[:160]}", flush=True)
                    shutil.rmtree(tdir, ignore_errors=True)
                    shutil.rmtree(gdir, ignore_errors=True)
                    consecutive_errs += 1
                    continue

                (tdir / "TASK.md").write_text(
                    format_swe_task_md(norm_repo, iid, str(row["problem_statement"]), "pytest"), encoding="utf-8"
                )
                gdir.mkdir(parents=True, exist_ok=True)
                (gdir / "gold_patch.diff").write_text(bug_patch, encoding="utf-8")
                swe_spec = {
                    "instance_id": iid,
                    "repo": norm_repo,
                    "raw_repo": raw_repo,
                    "runner": "pytest",
                    "venv_dir": str(vdir),
                    "reverse_gold_patch": True,  # git apply -R reverts bug_patch -> GOLD!
                    "fail_to_pass": f2p,
                    "pass_to_pass": p2p,
                }
                (gdir / "swe_spec.json").write_text(json.dumps(swe_spec, indent=2) + "\n", encoding="utf-8")

            # Verify gate: buggy workspace MUST fail cleanly, reversing bug_patch (GOLD) MUST pass 100%
            res_bug = grade_swe_dir(gdir, tdir, timeout=45, venv_dir=vdir, apply_gold=False)
            if res_bug["status"] != "fail":
                print(f"  [rej {iid}] bug status={res_bug['status']} detail={res_bug.get('detail','')} tail={(res_bug.get('stdout_tail','')+res_bug.get('stderr',''))[-160:]}", flush=True)
                shutil.rmtree(tdir, ignore_errors=True)
                shutil.rmtree(gdir, ignore_errors=True)
                consecutive_errs += 1
                continue
            res_gold = grade_swe_dir(gdir, tdir, timeout=45, venv_dir=vdir, apply_gold=True)
            if res_gold["status"] != "pass":
                print(f"  [rej {iid}] gold status={res_gold['status']} detail={res_gold.get('detail','')} tail={(res_gold.get('stdout_tail','')+res_gold.get('stderr',''))[-160:]}", flush=True)
                shutil.rmtree(tdir, ignore_errors=True)
                shutil.rmtree(gdir, ignore_errors=True)
                consecutive_errs += 1
                continue

            consecutive_errs = 0
            got += 1
            accepted.append({
                "id": iid,
                "split": "train",
                "kind": "swe_verified",
                "domain": f"smith_{slug}",
                "repo": norm_repo,
                "venv_dir": str(vdir),
                "passed": {
                    "base": f"{res_bug['passed']}/{res_bug['total']}",
                    "gold": f"{res_gold['passed']}/{res_gold['total']}",
                },
            })
            print(f"  [OK {got}/{want}] {iid} ({res_bug['passed']}/{res_bug['total']} -> {res_gold['passed']}/{res_gold['total']})", flush=True)

    used_repos = {a["repo"] for a in accepted}
    assert not (used_repos & SWE_VERIFIED_ALL_REPOS), f"Contamination detected: {used_repos & SWE_VERIFIED_ALL_REPOS}"

    accepted.sort(key=lambda r: r["id"])
    (out_dir / "manifest.json").write_text(json.dumps({"tasks": accepted}, indent=2) + "\n", encoding="utf-8")
    summary = {
        "source": dataset_name,
        "n_train_tasks": len(accepted),
        "zero_overlap_with_swe_verified": True,
        "by_repo": dict(Counter(a["repo"] for a in accepted)),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("\n=== SWE-SMITH-PY MULTI-FILE TRAINING POOL READY ===", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data" / "swe_smith_v1")
    ap.add_argument("--venv-root", type=Path, default=Path("/content/swe_venvs"))
    ap.add_argument("--clone-root", type=Path, default=Path("/content/swe_mirrors"))
    ap.add_argument("--max-total", type=int, default=160)
    ap.add_argument("--max-per-repo", type=int, default=16)
    args = ap.parse_args()
    build_swe_smith_train(args.out_dir, args.venv_root, args.clone_root, args.max_total, args.max_per_repo)


if __name__ == "__main__":
    main()
