"""Run actual OpenCode against the isolated synthetic relay and verify evidence."""

from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
import secrets
import shutil
import tempfile
import time

from agent import LocalEndpoint, agent_sandbox, json_lines, run_agent, verify_cli
from containers import Docker, IMAGE, ROOT
from grade import grade, read_submission
from protocol import verify_fixtures
from run import prepare_task, record_patch
from colab.contracts import policy_trial, targets, trace_segments

from .relay import MODEL, PORT
from .seal import SOURCE, save, seal, verify
from .trace import validate_turn


def expect(condition, failure):
    if not condition:
        raise RuntimeError(failure)


@contextmanager
def service(docker, component, ipc, runtime):
    name = docker.name(component)
    args = docker.sandbox(name) + ["-d", "--log-driver=local", "--workdir=/app"]
    args += docker.mount(runtime, "/app/capture")
    args += docker.mount(ipc, "/ipc", writable=component == "fixture_engine")
    try:
        limit, code, out, err = docker.invoke(args + [IMAGE, "python", "-E", "-s", "-B", "-u", "-m",
                                                    "capture." + component])
        expect(not limit and code == 0, f"could not start {component}: {err or out}")
        for _ in range(25):
            limit, code, out, err = docker.invoke(["logs", name])
            expect(not limit and code == 0 and not err, f"{component} did not start: {err or out}")
            if any(item.get("event") == "ready" for item in json_lines(out)):
                break
            time.sleep(0.12)
        else:
            raise RuntimeError(f"{component} did not become ready")
        yield name
    finally:
        docker.remove(name)


def collect(docker, name, path):
    limit, code, out, err = docker.invoke(["logs", name])
    expect(not limit and code == 0 and not err, f"unexpected service log failure: {err}")
    path.write_text(out, encoding="utf-8")
    return json_lines(out)


def trace_doc(events, engine, cli_events):
    committed = [item for item in events if item["event"] == "committed"]
    ids = {item["request_sha256"] for item in committed}
    expect(len(committed) == len(ids), "a request was committed twice")
    nodes = set()
    for item in committed:
        turn = item["synthetic_capture"]
        validate_turn(turn)
        expect(turn["node_id"] not in nodes, "duplicate capture node")
        nodes.add(turn["node_id"])
    retried = [item for item in events if item["event"] == "upstream_interrupted"]
    expect(len(retried) == 1 and retried[0]["attempt"] == 1 and any(
        item["request_sha256"] == retried[0]["request_sha256"] and item["attempt"] == 2
        and item["synthetic_capture"]["purpose"] == "read" for item in committed),
        "read did not retry exactly once before commit")
    cuts = [item for item in engine if item["event"] == "fixture_cut"]
    expect(len(cuts) == 1 and cuts[0]["request_sha256"] == retried[0]["request_sha256"],
           "fixture did not cut the retried stream")
    replays = [item for item in events if item["event"] == "deduplicated"]
    rejected = [item for item in events if item["event"] == "capture_rejected"]
    expect(len(replays) == 1 and replays[0]["request_sha256"] in ids and sum(
        item["event"] == "fixture_completed" and item["request_sha256"] == replays[0]["request_sha256"]
        for item in engine) == 1, "replay issued unexpected upstream requests")
    expect(len(rejected) == 2 and not ids.intersection(item["request_sha256"] for item in rejected)
           and any("prompt_token_ids" in item["detail"] for item in rejected)
           and any("per_token_logps" in item["detail"] for item in rejected)
           and all(sum(row["event"] == "fixture_completed" and row["request_sha256"] == item["request_sha256"]
                       for row in engine) == 1 for item in rejected), "invalid capture was committed or retried")
    turns = [item["synthetic_capture"] for item in committed
             if item["synthetic_capture"]["purpose"] in ("read", "edit", "final")]
    expect([turn["purpose"] for turn in turns] == ["read", "edit", "final"], "unexpected tool turn sequence")
    edit = turns[1]
    expect(edit["prompt_token_ids"][-2:] == [70, 71] and edit["loss_mask"][4:6] == [0, 0]
           and [token for _, token, _ in targets(edit)] == [22, 23], "tool result entered the loss targets")
    segments = trace_segments(turns)
    expect([row["segment"] for row in segments] == [0, 0, 1], "rewrite did not form a separate segment")
    calls = [item["part"] for item in cli_events if item["type"] == "tool_use"]
    expect([(item["tool"], item["state"]["status"]) for item in calls] ==
           [("read", "completed"), ("edit", "completed")], "OpenCode did not complete one read and one edit")
    return {"source": SOURCE, "usable_for_grpo": False, "real_engine_trace": False, "task_id": "boundary",
            "turns": turns, "segments": segments, "completed_cli_tools": ["read", "edit"],
            "stream_retries": len(retried), "dedup_replays": len(replays), "capture_rejections": len(rejected)}


def run(output):
    verify_fixtures()
    docker = Docker()
    docker.prepare()
    output.mkdir(parents=True, exist_ok=False)
    print(f"Relay artifacts: {output}", flush=True)
    (output / "cli-verification.txt").write_text(verify_cli(docker), encoding="utf-8")
    with ExitStack() as stack:
        runtime = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="oca-relay-runtime-")))
        runtime.chmod(0o755)
        for name in ("__init__.py", "relay.py", "trace.py", "fixture_engine.py"):
            shutil.copyfile(ROOT / "capture" / name, runtime / name)
            (runtime / name).chmod(0o444)
        ipc = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="oca-relay-ipc-")))
        ipc.chmod(0o777)
        sentinel = ipc / "session"
        sentinel.write_text("synthetic-" + secrets.token_hex(24))
        sentinel.chmod(0o444)
        work = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="oca-relay-task-")))
        prepare_task("boundary", work)
        original = read_submission(work / "solution.py")
        engine = stack.enter_context(service(docker, "fixture_engine", ipc, runtime))
        relay = stack.enter_context(service(docker, "relay", ipc, runtime))
        endpoint = LocalEndpoint(relay, MODEL, PORT)
        limit, code, cli, err = run_agent(docker, work, (work / "TASK.md").read_text(), endpoint)
        (output / "cli-events.jsonl").write_text(cli, encoding="utf-8")
        (output / "cli-stderr.txt").write_text(err, encoding="utf-8")
        expect(not limit and code == 0, f"OpenCode failed: {limit or code} ({err})")

        probe_name = docker.name("relay-probe")
        args = agent_sandbox(docker, probe_name, work, endpoint)
        try:
            limit, code, out, err = docker.invoke(args + [
                IMAGE, "python", "-I", "-B", "-c", (ROOT / "capture" / "agent_probe.py").read_text(),
                str(PORT), MODEL,
            ], timeout=22)
        finally:
            docker.remove(probe_name)
        expect(not limit and code == 0, f"isolated agent probe failed: {err or out}")
        save(output / "isolation.json", json.loads(out))
        capture = collect(docker, relay, output / "relay.jsonl")
        upstream = collect(docker, engine, output / "engine.jsonl")
        trace = trace_doc(capture, upstream, json_lines(cli))
        save(output / "trace.json", trace)
        verdict = grade(docker, "boundary", work / "solution.py")
        save(output / "grade.json", verdict)
        record_patch(output, original, read_submission(work / "solution.py"))
        expect(verdict["status"] == "pass" and (output / "final.patch").stat().st_size > 0,
               "independent grading did not accept the edited result")
    try:
        policy_trial(trace, output)
    except ValueError as exc:
        expect("need genuine OpenEnv engine capture" in str(exc), f"unrelated training refusal: {exc}")
    else:
        raise RuntimeError("training admitted a synthetic trace")
    seal(output)
    verify(output)
    print("Synthetic relay passed; independent grade=pass, tools=read/edit, retries=1, replays=1, rejected=2.")
