"""Zero-contamination multi-file RL training set builder from `SWE-bench/SWE-smith-py`.

Strictly blacklists all 12 repositories present in `SWE-bench/SWE-bench_Verified` so training on
`SWE-smith-py` has 0% repository or instance overlap with heldout SWE-bench Verified evaluation.
Exports verified tasks (`base_commit` fails F2P, `gold_patch` passes 100% F2P+P2P) into `data/swe_smith_v1/`
with cached pure-Python `uv venv`s so `oca.train` consumes them natively alongside L1/L2 tasks.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil

from .. import ROOT
from .swe_verified import (
    SWE_VERIFIED_ALL_REPOS,
    ensure_git_mirror,
    ensure_repo_venv,
    export_commit,
    format_swe_task_md,
    grade_swe_dir,
    parse_swe_test_list,
)

# Curated lightweight pure-Python OSS repos present in SWE-smith-py (0% overlap with SWE-bench Verified!)
PREFERRED_SMITH_REPOS = {
    "pypa/packaging": ["pytest"],
    "pallets/click": ["pytest"],
    "pallets/jinja": ["pytest", "markupsafe"],
    "pallets/itsdangerous": ["pytest"],
    "more-itertools/more-itertools": ["pytest"],
    "encode/httpx": ["pytest", "anyio", "httpcore", "certifi", "idna", "sniffio"],
    "python-attrs/attrs": ["pytest", "hypothesis"],
    "marshmallow-code/marshmallow": ["pytest"],
    "Textualize/rich": ["pytest", "markdown-it-py", "pygments"],
    "hukkin/tomli": ["pytest"],
    "yaml/pyyaml": ["pytest"],
    "dateutil/dateutil": ["pytest", "six", "hypothesis"],
    "pyjwt/pyjwt": ["pytest"],
    "jd/tenacity": ["pytest"],
    "facelessuser/soupsieve": ["pytest"],
}

# Sanity assertion at import time: guaranteed zero repo leakage with SWE-bench Verified
assert not (set(PREFERRED_SMITH_REPOS) & SWE_VERIFIED_ALL_REPOS), "Repo leakage with SWE-bench Verified!"


def _normalize_repo_name(raw_repo: str) -> str:
    """SWE-smith repos may appear as `swesmith/owner__name.commit` or `owner/name`."""
    s = raw_repo.strip()
    if s.startswith("swesmith/"):
        s = s[len("swesmith/"):]
    s = s.split(".", 1)[0]
    if "__" in s and "/" not in s:
        s = s.replace("__", "/", 1)
    return s


def build_swe_smith_train(
    out_dir: Path,
    venv_root: Path,
    clone_root: Path,
    max_total: int = 160,
    max_per_repo: int = 20,
    dataset_name: str = "SWE-bench/SWE-smith-py",
) -> dict:
    from datasets import load_dataset

    print(f"[swe_smith] streaming {dataset_name} (blacklisting {len(SWE_VERIFIED_ALL_REPOS)} SWE-bench Verified repos)...", flush=True)
    ds = load_dataset(dataset_name, split="train", streaming=True)

    buckets: dict[str, list[dict]] = {r: [] for r in PREFERRED_SMITH_REPOS}
    scanned = 0
    for row in ds:
        scanned += 1
        norm_repo = _normalize_repo_name(str(row.get("repo") or ""))
        if norm_repo in SWE_VERIFIED_ALL_REPOS:
            continue
        if norm_repo not in buckets or len(buckets[norm_repo]) >= max_per_repo * 2:
            if all(len(v) >= max_per_repo * 2 for v in buckets.values()) or scanned >= 40_000:
                break
            continue
        if not (row.get("problem_statement") and row.get("patch") and row.get("FAIL_TO_PASS")):
            continue
        buckets[norm_repo].append({**dict(row), "_norm_repo": norm_repo})

    out_dir.mkdir(parents=True, exist_ok=True)
    accepted: list[dict] = []

    for repo, deps in PREFERRED_SMITH_REPOS.items():
        if len(accepted) >= max_total:
            break
        cands = buckets.get(repo) or []
        if not cands:
            continue
        slug = repo.split("/")[-1].lower().replace("-", "_")
        want = min(max_per_repo, max_total - len(accepted))
        print(f"[swe_smith] verifying {repo} (want {want} from {len(cands)} candidates)...", flush=True)
        try:
            vdir = ensure_repo_venv(venv_root, f"smith_{slug}", deps)
            mirror = ensure_git_mirror(clone_root, repo)
        except Exception as e:
            print(f"  [skip repo {repo}] setup err: {e}", flush=True)
            continue

        got = 0
        for row in cands:
            if got >= want:
                break
            raw_id = str(row.get("instance_id") or f"smith-{slug}-{got}")
            iid = f"smith-{raw_id}" if not raw_id.startswith("smith-") else raw_id
            iid = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in iid)[:72]
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
                except Exception:
                    continue
                (tdir / "TASK.md").write_text(
                    format_swe_task_md(repo, iid, str(row["problem_statement"]), "pytest"), encoding="utf-8"
                )
                gdir.mkdir(parents=True, exist_ok=True)
                (gdir / "test_patch.diff").write_text(str(row.get("test_patch") or ""), encoding="utf-8")
                (gdir / "gold_patch.diff").write_text(str(row.get("patch") or ""), encoding="utf-8")
                swe_spec = {
                    "instance_id": iid,
                    "repo": repo,
                    "base_commit": row["base_commit"],
                    "runner": "pytest",
                    "venv_dir": str(vdir),
                    "fail_to_pass": f2p,
                    "pass_to_pass": p2p,
                }
                (gdir / "swe_spec.json").write_text(json.dumps(swe_spec, indent=2) + "\n", encoding="utf-8")

            res_base = grade_swe_dir(gdir, tdir, timeout=60, venv_dir=vdir, apply_gold=False)
            if res_base["status"] != "fail":
                shutil.rmtree(tdir, ignore_errors=True)
                shutil.rmtree(gdir, ignore_errors=True)
                continue
            res_gold = grade_swe_dir(gdir, tdir, timeout=60, venv_dir=vdir, apply_gold=True)
            if res_gold["status"] != "pass":
                shutil.rmtree(tdir, ignore_errors=True)
                shutil.rmtree(gdir, ignore_errors=True)
                continue

            got += 1
            accepted.append({
                "id": iid,
                "split": "train",
                "kind": "swe_verified",
                "domain": f"smith_{slug}",
                "repo": repo,
                "base_commit": row["base_commit"],
                "venv_dir": str(vdir),
                "passed": {
                    "base": f"{res_base['passed']}/{res_base['total']}",
                    "gold": f"{res_gold['passed']}/{res_gold['total']}",
                },
            })
            print(f"  [OK {got}/{want}] {iid} ({res_base['passed']}/{res_base['total']} -> {res_gold['passed']}/{res_gold['total']})", flush=True)

    # Final assertion: ZERO overlap with SWE-bench Verified repositories
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
    ap.add_argument("--max-per-repo", type=int, default=20)
    args = ap.parse_args()
    build_swe_smith_train(args.out_dir, args.venv_root, args.clone_root, args.max_total, args.max_per_repo)


if __name__ == "__main__":
    main()
