"""Validate generated task sets (both `single_file` and multi-file `repo_pytest`).

Invariants enforced per task:
- Triple control: original=fail, reference=pass (100%), partial=fail
- Strict progress: passed(original) < passed(partial) < passed(reference) == total
- >= 6 hidden tests / cases
- For `repo_pytest`: >= 2 non-test Python source modules + visible tests passing on reference.
"""
import json
from pathlib import Path
import sys

from .grade import grade_file, grade_repo


def check_task(task_dir: Path, grader_dir: Path):
    problems = []
    for f in ("TASK.md", "solution.py"):
        if not (task_dir / f).is_file():
            problems.append(f"missing tasks/{f}")
    for f in ("cases.json", "reference.py", "partial.py"):
        if not (grader_dir / f).is_file():
            problems.append(f"missing grader/{f}")
    if problems:
        return {"ok": False, "problems": problems}
    extra = sorted(p.name for p in task_dir.iterdir() if p.name not in ("TASK.md", "solution.py"))
    if extra:
        problems.append(f"unexpected files in task dir: {extra}")
    spec = json.loads((grader_dir / "cases.json").read_text(encoding="utf-8"))
    cases = spec.get("cases", [])
    if len(cases) < 6:
        problems.append(f"only {len(cases)} cases (need >=6)")
    if len({c.get('id') for c in cases}) != len(cases):
        problems.append("duplicate case ids")
    if f"`{spec.get('function')}" not in (task_dir / "TASK.md").read_text(encoding="utf-8"):
        problems.append("TASK.md does not name the graded function in backticks")
    res = {v: grade_file(grader_dir, p) for v, p in (("original", task_dir / "solution.py"),
                                                    ("reference", grader_dir / "reference.py"),
                                                    ("partial", grader_dir / "partial.py"))}
    st = {k: v["status"] for k, v in res.items()}
    if st["original"] not in ("fail", "test_error"):
        problems.append(f"original should fail, got {st['original']}")
    if st["reference"] != "pass":
        problems.append(f"reference should pass, got {st['reference']} {res['reference'].get('detail', '')} "
                        f"{[c['id'] for c in res['reference'].get('cases', []) if c['status'] != 'pass']}"
                        f" {res['reference'].get('stderr', '')[-400:]}")
    if st["partial"] not in ("fail", "test_error"):
        problems.append(f"partial should fail, got {st['partial']}")
    if res["partial"].get("passed", 0) <= res["original"].get("passed", 0):
        problems.append(f"partial must pass more cases than original "
                        f"({res['partial'].get('passed')} vs {res['original'].get('passed')})")
    return {"ok": not problems, "problems": problems, "status": st,
            "passed": {k: f"{v.get('passed')}/{v.get('total')}" for k, v in res.items()}}


def check_repo_task(task_dir: Path, grader_dir: Path, require_partial: bool = True):
    """Validate a multi-file `repo_pytest` task (synthetic or real OSS OOD)."""
    problems = []
    if not (task_dir / "TASK.md").is_file():
        problems.append("missing TASK.md")
    if not (grader_dir / "tests_hidden").is_dir():
        problems.append("missing grader/tests_hidden/")
    if not (grader_dir / "reference").is_dir():
        problems.append("missing grader/reference/")
    if require_partial and not (grader_dir / "partial").is_dir():
        problems.append("missing grader/partial/")
    if problems:
        return {"ok": False, "problems": problems}

    src_py = [
        p for p in task_dir.rglob("*.py")
        if "test" not in p.parts and not p.name.startswith("test_") and "__pycache__" not in p.parts
    ]
    if len(src_py) < 2:
        problems.append(f"repo_pytest must have >=2 non-test .py modules, found {len(src_py)}")

    variants = [("original", task_dir), ("reference", grader_dir / "reference")]
    if require_partial:
        variants.append(("partial", grader_dir / "partial"))
    res = {v: grade_repo(grader_dir, p, timeout=20) for v, p in variants}
    st = {k: v["status"] for k, v in res.items()}
    total = res["reference"].get("total", 0)
    if total < 6:
        problems.append(f"only {total} hidden pytest cases (need >=6)")
    if st["original"] not in ("fail", "test_error"):
        problems.append(f"original should fail hidden tests, got {st['original']}")
    if st["reference"] != "pass":
        problems.append(f"reference should pass all hidden tests, got {st['reference']} "
                        f"({res['reference'].get('passed')}/{total}) {res['reference'].get('stdout_tail', '')[-400:]}")
    if require_partial:
        if st["partial"] not in ("fail", "test_error"):
            problems.append(f"partial should fail hidden tests, got {st['partial']}")
        if res["partial"].get("passed", 0) <= res["original"].get("passed", 0):
            problems.append(f"partial must pass more hidden tests than original "
                            f"({res['partial'].get('passed')} vs {res['original'].get('passed')})")

    # If visible tests/ exist, verify reference also passes visible tests
    if (task_dir / "tests").is_dir():
        vis_ref = grade_repo(task_dir, grader_dir / "reference", timeout=15, tests_subdir="tests")
        if vis_ref["status"] != "pass":
            problems.append(f"reference failed visible tests/: {vis_ref.get('stdout_tail', '')[-300:]}")

    return {"ok": not problems, "problems": problems, "status": st,
            "src_modules": len(src_py),
            "passed": {k: f"{v.get('passed')}/{v.get('total')}" for k, v in res.items()}}


def validate_set(base: Path):
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    out = {}
    for row in manifest["tasks"]:
        kind = row.get("kind", "single_file")
        td, gd = base / "tasks" / row["id"], base / "grader" / row["id"]
        if kind == "repo_pytest":
            out[row["id"]] = check_repo_task(td, gd, require_partial=not base.name.startswith("ood_"))
        else:
            out[row["id"]] = check_task(td, gd)
    listed = {row["id"] for row in manifest["tasks"]}
    for d in (base / "tasks").iterdir() if (base / "tasks").is_dir() else []:
        if d.name not in listed:
            out[d.name] = {"ok": False, "problems": ["directory not listed in manifest.json"]}
    return out


if __name__ == "__main__":
    base = Path(sys.argv[1])
    results = validate_set(base)
    for tid, r in results.items():
        line = f"{tid:36} {'OK ' if r['ok'] else 'BAD'} {r.get('passed', '')}"
        print(line)
        for p in r["problems"]:
            print("    -", p)
    good = sum(r["ok"] for r in results.values())
    print(f"{good}/{len(results)} valid")
    raise SystemExit(0 if good == len(results) else 1)
