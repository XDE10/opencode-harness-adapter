"""Task registry: v3 fixtures, cleaned single-file sets, multi-file repo_pytest, SWE-smith & SWE-bench Verified."""
from dataclasses import dataclass
import json
from pathlib import Path

from . import ROOT


@dataclass(frozen=True)
class Task:
    id: str
    split: str                  # train | heldout | pilot | swe_verified
    task_dir: Path              # visible workspace (TASK.md + solution.py OR full repo)
    grader_dir: Path            # hidden grader (cases.json | tests_hidden | swe_spec.json+test_patch.diff)
    source: str = "v3"
    kind: str = "single_file"   # single_file | repo_pytest | swe_verified
    domain: str = ""
    venv_dir: str = ""          # optional isolated uv venv path for real OSS repos

    @property
    def prompt(self) -> str:
        return (self.task_dir / "TASK.md").read_text(encoding="utf-8")


def _v3():
    manifest = json.loads((ROOT / "protocol" / "first-batch-v3.json").read_text(encoding="utf-8"))
    for row in manifest["tasks"]:
        yield Task(row["id"], row["split"], ROOT / "tasks" / row["id"], ROOT / "grader" / row["id"],
                   source="v3", kind="single_file", domain=row.get("repo", "v3"))
    for pilot in ("boundary", "parsing", "serialization"):
        yield Task(pilot, "pilot", ROOT / "tasks" / pilot, ROOT / "grader" / pilot,
                   source="v3", kind="single_file", domain="pilot")


def _scan_data_manifests(glob_pattern: str, default_kind: str):
    data_dir = ROOT / "data"
    if not data_dir.is_dir():
        return
    for manifest in sorted(data_dir.glob(glob_pattern)):
        base = manifest.parent
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        for row in doc.get("tasks") or []:
            kind = row.get("kind") or default_kind
            tdir = Path(row["task_dir"]) if row.get("task_dir") else (base / "tasks" / row["id"])
            gdir = Path(row["grader_dir"]) if row.get("grader_dir") else (base / "grader" / row["id"])
            yield Task(
                id=row["id"],
                split=row["split"],
                task_dir=tdir,
                grader_dir=gdir,
                source=base.name,
                kind=kind,
                domain=row.get("domain", base.name),
                venv_dir=row.get("venv_dir", ""),
            )


def load(split=None, kind=None):
    tasks = {}
    for task in (
        *_v3(),
        *_scan_data_manifests("tasks-*/manifest.json", "single_file"),
        *_scan_data_manifests("repo_*/manifest.json", "repo_pytest"),
        *_scan_data_manifests("ood_*/manifest.json", "repo_pytest"),
        *_scan_data_manifests("swe_smith*/manifest.json", "swe_verified"),
        *_scan_data_manifests("swe_verified*/manifest.json", "swe_verified"),
    ):
        if task.id in tasks:
            raise ValueError(f"duplicate task id {task.id}")
        tasks[task.id] = task
    return [
        t for t in tasks.values()
        if (split is None or t.split == split) and (kind is None or t.kind == kind)
    ]


def by_id():
    return {t.id: t for t in load()}
