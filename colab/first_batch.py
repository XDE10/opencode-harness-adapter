"""Verify and grade the frozen CPU task batch by repository split."""

import argparse
import hashlib
import re
import tempfile
from pathlib import Path

from containers import Docker
from report import save_json
from run import controls

from .contracts import DATA_PATH, LEGACY_DATA_PATH, PILOT, ROOT, digest, read_json, require, validate_plan

SPLIT_SIZES = {1: (2, 1), 2: (6, 4), 3: (12, 12)}
MANIFESTS = {version: ROOT / "protocol" / f"first-batch-v{version}.json" for version in SPLIT_SIZES}
AGENT_FILES = ("TASK.md", "solution.py")


def verify_batch(root=ROOT, *, version=2):
    manifest = read_json(MANIFESTS[version])
    require(manifest["id"] == f"first-batch-v{version}", "unexpected batch ID")
    previous_ids = set()
    if version > 1:
        previous = verify_batch(root, version=version - 1)
        by_id = {row["id"]: row for row in manifest["tasks"]}
        require(manifest["base_batch_sha256"] == digest(MANIFESTS[version - 1]) and
                all(by_id.get(row["id"]) == row for row in previous["tasks"]),
                "batch did not retain the previous freeze")
        previous_ids = {row["id"] for row in previous["tasks"]}
    planned = {}
    if version < 3:
        plan_path = LEGACY_DATA_PATH if version == 1 else DATA_PATH
        data = read_json(plan_path)
        validate_plan(data, version=version)
        require(manifest["source_plan_sha256"] == digest(plan_path), "source split plan changed")
        planned = {(role, row["repo"]): row["revision"]
                   for role in ("train", "heldout") for row in data[role]}
    else:
        require(manifest["model_screening"] == "not_run", "v3 is a CPU-only candidate freeze")
    seen_tasks = set()
    repo_splits = {}
    for task in manifest["tasks"]:
        task_id, split, repo = (task[key] for key in ("id", "split", "repo"))
        require(re.fullmatch(r"[a-z0-9-]+", task_id) and split in ("train", "heldout"),
                "invalid task ID or split")
        require(task_id not in seen_tasks and task_id not in PILOT, "duplicate or pilot task in first batch")
        seen_tasks.add(task_id)
        if version < 3:
            require(planned.get((split, repo)) == task["revision"], "repository, split or revision differs from plan")
        require(repo not in repo_splits, "batch must contain at most one task per repository")
        repo_splits[repo] = split
        expected = {*(f"tasks/{task_id}/{name}" for name in AGENT_FILES),
                    *(f"grader/{task_id}/{name}" for name in ("cases.json", "reference.py", "partial.py"))}
        require(set(task["files"]) == expected, "task file inventory differs")
        for file, checksum in task["files"].items():
            require(digest(root / file) == checksum, f"frozen task changed: {file}")
        if version == 3 and task_id not in previous_ids:
            require(task.get("source") == "local_mini_repo" and re.fullmatch(r"oca-fixtures/[a-z0-9-]+", repo),
                    "new task must have a local mini-repository identity")
            snapshot = "".join(f"{task['files'][f'tasks/{task_id}/{name}']}  {name}\n" for name in AGENT_FILES)
            require(hashlib.sha256(snapshot.encode("ascii")).hexdigest() == task["revision"],
                    "local mini-repository revision differs from its snapshot")
    require(tuple(list(repo_splits.values()).count(role) for role in ("train", "heldout"))
            == SPLIT_SIZES[version], "unexpected batch split size")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-version", type=int, choices=MANIFESTS, default=2)
    args = parser.parse_args()
    manifest = verify_batch(version=args.manifest_version)
    by_id = {row["id"]: row for row in manifest["tasks"]}
    docker = Docker()
    docker.prepare()
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="batch-cpu-", dir=artifacts))
    print(f"Batch artifacts: {output}", flush=True)
    results = controls(docker, output, tasks=list(by_id), protocol_id=manifest["id"])
    summary = {"source": "cpu_grade_controls", "manifest_version": args.manifest_version,
               "manifest_sha256": digest(MANIFESTS[args.manifest_version]),
               "model_screening": "not_run",
               "results": [{**row, "split": by_id[row["task_id"]]["split"], "repo": by_id[row["task_id"]]["repo"]}
                           for row in results]}
    save_json(output / "summary.json", summary)
    return 0 if all(row["matches"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
