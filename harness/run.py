"""Run verifier controls, a scripted smoke, or a three-task local model pilot."""

import argparse
import difflib
from pathlib import Path
import tempfile
import time

from agent import (
    AGENT_TIMEOUT, AGENT_VERSION, CLI, MAX_OUTPUT_TOKENS, MOCK_MAX_CALLS, MODEL,
    json_lines, mock_backend, pilot_endpoint, run_agent, verify_cli,
)
from containers import Docker, IMAGE, ROOT
from grade import TIMEOUT, grade, read_submission
from protocol import LIMITS, PROTOCOL, verify_fixtures
from report import NO_TRAINING_TRACE, save_json as dump, save_manifest, write_report

TASKS = PROTOCOL["tasks"]
EXPECT = PROTOCOL["controls"]
PILOT_TIMEOUT = LIMITS["pilot_wall_s"]


def record_patch(directory, original, final):
    patch = difflib.unified_diff(original.splitlines(keepends=True), final.splitlines(keepends=True),
                                 fromfile="a/solution.py", tofile="b/solution.py")
    with directory.joinpath("final.patch").open("w", encoding="utf-8") as file:
        for line in patch:
            file.write(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")


def prepare_task(task, directory):
    task_dir = ROOT / "tasks" / task
    directory.chmod(0o777)
    for filename in ("TASK.md", "solution.py"):
        path = directory / filename
        path.write_bytes((task_dir / filename).read_bytes())
        path.chmod(0o666 if filename == "solution.py" else 0o444)


def base_record(task, kind, started, *, provenance):
    return {"schema_version": 2, "task_id": task, "run_kind": kind, "provenance": provenance,
            "protocol": PROTOCOL["id"],
            "container_image": IMAGE, "started_unix": started,
            "agent_version": None, "model_id": None,
            "call_budget": None, "tool_calls": [], "tool_call_count": 0, "tool_event_count": 0,
            "final_patch": "final.patch", "grade": None,
            "training_trajectory": NO_TRAINING_TRACE}


def capture_tools(record, events):
    calls = [event for event in events if event.get("type") == "tool_use"]
    completed = [call for call in calls if call["part"]["state"]["status"] == "completed"]
    record.update(tool_calls=calls, tool_call_count=len(completed), tool_event_count=len(calls))
    return calls, completed


def controls(docker, output, *, tasks=TASKS, protocol_id=PROTOCOL["id"]):
    results = []
    for task in tasks:
        for variant, expected in EXPECT.items():
            folder = output / f"{task}-{variant}"
            folder.mkdir()
            record = base_record(task, f"control:{variant}", time.time(), provenance="fixture_control")
            record["protocol"] = protocol_id
            start = time.monotonic()
            with tempfile.TemporaryDirectory(prefix="oca-task-") as tmp:
                work = Path(tmp)
                prepare_task(task, work)
                solution = work / "solution.py"
                original = read_submission(solution)
                if variant != "original":
                    solution.write_bytes((ROOT / "grader" / task / f"{variant}.py").read_bytes())
                record_patch(folder, original, read_submission(solution))
                verdict = grade(docker, task, solution)
            record.update(grade=verdict, expected_status=expected,
                          wall_seconds=round(time.monotonic() - start, 3))
            dump(folder / "record.json", record)
            matches = verdict["status"] == expected
            detail = ", ".join(case["id"] for case in verdict.get("cases", []) if case["status"] != "pass")
            print(f"{task:14} {variant:9} {verdict['status']:12} expected={expected} {detail or verdict.get('detail', '')}")
            results.append({"task_id": task, "variant": variant, "status": verdict["status"], "expected": expected,
                            "matches": matches, "record": f"{folder.name}/record.json"})
    return results


def smoke(docker, output):
    task = "boundary"
    folder = output / "boundary-cli-smoke"
    folder.mkdir()
    start = time.monotonic()
    record = base_record(task, "scripted_local_smoke", time.time(), provenance="scripted_mock")
    record.update(agent_version=AGENT_VERSION, model_id=MODEL,
                  call_budget={"max_completion_requests": MOCK_MAX_CALLS,
                               "max_wall_seconds": AGENT_TIMEOUT,
                               "configured_max_output_tokens_per_request": MAX_OUTPUT_TOKENS},
                  grader_timeout_seconds=TIMEOUT,
                  cli_events="cli-events.jsonl", mock_events="mock-events.jsonl")
    mock_out, mock_err, out, err = "", "", "", ""
    status = "agent_error"
    with tempfile.TemporaryDirectory(prefix="oca-task-") as tmp:
        work = Path(tmp)
        prepare_task(task, work)
        solution = work / "solution.py"
        original = read_submission(solution)
        try:
            with mock_backend(docker) as endpoint:
                try:
                    pilot_endpoint(docker, endpoint.container, "probe-only", endpoint.port, "probe-only")
                except RuntimeError as exc:
                    if "scripted mock cannot be used as a model pilot" not in str(exc):
                        raise
                    record["pilot_mock_rejected"] = True
                else:
                    raise RuntimeError("scripted mock passed model preflight")
                limit, code, out, err = run_agent(docker, work, (work / "TASK.md").read_text(), endpoint)
                _, _, mock_out, mock_err = docker.invoke(["logs", endpoint.container])
        except (OSError, RuntimeError) as exc:
            record["detail"] = str(exc)
        else:
            record.update(agent_exit_code=code, agent_limit=limit)
            model_events = [event for event in json_lines(mock_out) if "request" in event]
            requests = [event for event in model_events if event.get("event") == "completion"]
            calls, completed = capture_tools(record, json_lines(out))
            record.update(completion_requests=len(model_events), successful_mock_responses=len(requests))
            status = "agent_timeout" if limit == "timeout" else "agent_error"
            if not limit and code == 0:
                task_requests = [request for request in requests if request["purpose"] == "task"]
                expected_results = [[], ["call_smoke_read"], ["call_smoke_read", "call_smoke_write"]]
                if (len(model_events) == len(requests) and len(calls) == len(completed)
                        and [call["part"]["tool"] for call in completed] == ["read", "write"]
                        and [request["tool_results"] for request in task_requests] == expected_results):
                    record["grade"] = grade(docker, task, solution)
                    status = record["grade"]["status"]
                else:
                    record["detail"] = "CLI events or mock tool-result round trip did not match"
        try:
            record_patch(folder, original, read_submission(solution))
        except (OSError, ValueError) as exc:
            record.update(final_patch=None, patch_error=str(exc))
    for file, data in (("cli-events.jsonl", out), ("cli-stderr.txt", err),
                       ("mock-events.jsonl", mock_out), ("mock-stderr.txt", mock_err)):
        folder.joinpath(file).write_text(data, encoding="utf-8")
    record.update(status=status, wall_seconds=round(time.monotonic() - start, 3))
    dump(folder / "record.json", record)
    print(f"CLI smoke      {status}  requests={record.get('completion_requests', 0)} "
          f"tools={record['tool_call_count']}")
    return status


def pilot_attempt(docker, task, folder, endpoint, endpoint_identity):
    folder.mkdir()
    start = time.monotonic()
    record = base_record(task, "local_model_pilot", time.time(), provenance="operator_endpoint")
    record.update(agent_version=AGENT_VERSION, model_id=f"local/{endpoint.model_id}",
                  model_revision=endpoint_identity["model_revision"],
                  call_budget={"max_wall_seconds": PILOT_TIMEOUT,
                               "configured_max_output_tokens_per_request": MAX_OUTPUT_TOKENS,
                               "max_completion_requests": None},
                  completion_requests=None, grader_timeout_seconds=TIMEOUT, cli_events="cli-events.jsonl")
    out, err = "", ""
    with tempfile.TemporaryDirectory(prefix="oca-pilot-") as tmp:
        work = Path(tmp)
        prepare_task(task, work)
        solution = work / "solution.py"
        original = read_submission(solution)
        status = "agent_error"
        try:
            limit, code, out, err = run_agent(docker, work, (work / "TASK.md").read_text(), endpoint,
                                              timeout=PILOT_TIMEOUT)
        except (OSError, RuntimeError) as exc:
            record["detail"] = str(exc)
        else:
            events = json_lines(out)
            capture_tools(record, events)
            record.update(agent_exit_code=code, agent_limit=limit)
            types = {event.get("type") for event in events}
            if limit == "timeout":
                status = "agent_timeout"
            elif not limit and code == 0 and "error" not in types and "step_finish" in types:
                try:
                    record["grade"] = grade(docker, task, solution)
                except (OSError, RuntimeError) as exc:
                    record["grade"] = {"status": "test_error", "detail": str(exc)}
                status = record["grade"]["status"]
            else:
                record["detail"] = "CLI did not finish a model step successfully; see CLI logs"
        try:
            record_patch(folder, original, read_submission(solution))
        except (OSError, ValueError) as exc:
            record.update(final_patch=None, patch_error=str(exc))
    (folder / "cli-events.jsonl").write_text(out, encoding="utf-8")
    (folder / "cli-stderr.txt").write_text(err, encoding="utf-8")
    record.update(status=status, wall_seconds=round(time.monotonic() - start, 3))
    dump(folder / "record.json", record)
    tools = [call["part"]["tool"] for call in record["tool_calls"]]
    print(f"{task:14} {status:14} tools={','.join(tools) or '-'} "
          f"completed={record['tool_call_count']} patch={record['final_patch'] or '-'}", flush=True)
    return {"task_id": task, "status": status, "tool_call_count": record["tool_call_count"],
            "record": f"{folder.name}/record.json"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--controls-only", action="store_true")
    mode.add_argument("--smoke-only", action="store_true")
    mode.add_argument("--pilot-container", metavar="NAME", help="running model container with --network none")
    parser.add_argument("--model", help="exact model ID advertised by the pilot container")
    parser.add_argument("--model-revision", help="authorized weight revision, supplied by the operator")
    parser.add_argument("--port", type=int, help="loopback API port inside the pilot container (default: 8000)")
    args = parser.parse_args()
    if args.pilot_container:
        if not args.model or not args.model_revision or not args.model.strip() or not args.model_revision.strip():
            parser.error("--pilot-container requires --model and --model-revision")
        if args.port is not None and not 1 <= args.port <= 65535:
            parser.error("--port must be between 1 and 65535")
    elif any(value is not None for value in (args.model, args.model_revision, args.port)):
        parser.error("--model, --model-revision and --port require --pilot-container")
    try:
        verify_fixtures()
    except (OSError, RuntimeError) as exc:
        parser.exit(2, f"Protocol check failed: {exc}\n")
    if not args.controls_only and not CLI.is_file():
        parser.error("run scripts/install-opencode.sh first")
    docker = Docker()
    docker.prepare()
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix="run-", dir=artifacts))
    print(f"Artifacts: {output}", flush=True)
    run_mode = "endpoint_pilot" if args.pilot_container else (
        "fixture_controls" if args.controls_only else "cpu_acceptance")
    save_manifest(output, run_mode, None if args.controls_only else CLI)
    if args.pilot_container:
        preflight = {"container": args.pilot_container, "model_id": args.model,
                     "model_revision": args.model_revision, "port": args.port or 8000}
        try:
            endpoint, identity = pilot_endpoint(docker, args.pilot_container, args.model,
                                                preflight["port"], args.model_revision)
        except (OSError, ValueError, RuntimeError) as exc:
            dump(output / "preflight.json", {**preflight, "status": "rejected", "detail": str(exc)})
            write_report(output, [], mode=run_mode)
            parser.exit(2, f"Pilot not started: {exc}\n")
        dump(output / "preflight.json", {**preflight, **identity, "status": "ready"})
    verification_file = None
    if not args.controls_only:
        verification = verify_cli(docker)
        verification_file = "cli-verification.txt"
        (output / verification_file).write_text(verification, encoding="utf-8")
        print(verification.splitlines()[0] + " | opencode run --help: OK", flush=True)
    if args.pilot_container:
        results = [pilot_attempt(docker, task, output / f"{task}-pilot", endpoint, identity) for task in TASKS]
        write_report(output, [item["record"] for item in results], mode=run_mode)
        dump(output / "summary.json", {"pilot": results, "cli_verification": verification_file})
        return 0 if all(item["status"] in ("pass", "fail") for item in results) else 1
    checks = [] if args.smoke_only else controls(docker, output)
    status = None if args.controls_only else smoke(docker, output)
    record_paths = [item["record"] for item in checks]
    if status is not None:
        record_paths.append("boundary-cli-smoke/record.json")
    write_report(output, record_paths, mode=run_mode)
    dump(output / "summary.json", {"fixture_checks": checks, "cli_smoke": status,
                                   "cli_verification": verification_file})
    return 0 if all(item["matches"] for item in checks) and status in (None, "pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
