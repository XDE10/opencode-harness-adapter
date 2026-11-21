"""Auditable CLI evaluation reports, separate from model training capture."""

from collections import Counter
import json
import subprocess

from protocol import PIN, PROTOCOL, ROOT, sha256

NO_TRAINING_TRACE = {"available": False, "usable_for_grpo": False, "source": None,
                     "token_ids": None, "logprobs": None, "training_mask": None}


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def save_manifest(output, mode, cli):
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True)
    paths = sorted(path for folder, pattern in (("harness", "*.py"), ("tests", "*.py"), ("scripts", "*.sh"))
                   for path in (ROOT / folder).glob(pattern))
    save_json(output / "manifest.json", {
        "run_id": output.name, "mode": mode, "git_head": git.stdout.strip() if git.returncode == 0 else None,
        "protocol": PROTOCOL, "protocol_sha256": sha256(PIN),
        "implementation_sha256": {str(path.relative_to(ROOT)): sha256(path) for path in paths},
        "cli_sha256": sha256(cli) if cli is not None else None,
        "model_sampling": "scripted" if mode == "cpu_acceptance" else (
            "endpoint_defaults_unverified" if mode == "endpoint_pilot" else None),
    })


def write_report(output, record_paths, *, mode):
    attempts = []
    counts = {}
    for relative in record_paths:
        path = output / relative
        record = json.loads(path.read_text(encoding="utf-8"))
        grade = record["grade"]
        grade_status = grade["status"] if grade else None
        status = record.get("status", grade_status)
        source = record["provenance"]
        counts.setdefault(source, Counter())[status] += 1
        files = {"record": relative}
        for field in ("final_patch", "cli_events", "mock_events"):
            name = record.get(field)
            if name and (file := path.parent / name).is_file():
                files[field] = str(file.relative_to(output))
        attempts.append({
            "task_id": record["task_id"], "kind": record["run_kind"], "provenance": source,
            "agent_version": record["agent_version"], "model_id": record["model_id"],
            "status": status, "correctness_reward": {"pass": 1, "fail": 0}.get(grade_status),
            "wall_seconds": record["wall_seconds"],
            "observed_cli_tool_events": record["tool_event_count"],
            "completed_cli_tool_calls": record["tool_call_count"],
            "mock_http_completion_requests": record.get("completion_requests") if source == "scripted_mock" else None,
            "model_calls": None, "model_generated_tokens": None,
            "files": {key: {"path": value, "sha256": sha256(output / value)} for key, value in files.items()},
            "training_trajectory": NO_TRAINING_TRACE,
        })

    save_json(output / "trajectory-report.json", {
        "schema_version": 1, "run_id": output.name, "mode": mode, "source": "opencode_cli_and_independent_grader",
        "manifest": "manifest.json", "preflight": "preflight.json" if mode == "endpoint_pilot" else None,
        "status_counts_by_provenance": counts, "attempts": attempts,
    })
