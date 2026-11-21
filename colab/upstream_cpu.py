"""One bounded offline trial through Harbor's scheduler and pinned OpenEnv capture."""

import asyncio
from contextlib import ExitStack, contextmanager
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import sys
import sysconfig
import tempfile
import time
import uuid

from harbor.models.task.task import Task
from agent import CLI, json_lines, verify_cli
from containers import Docker, IMAGE, ROOT
from grade import read_submission
from protocol import verify_fixtures
from run import record_patch
from capture.openenv_cpu_service import MODEL, SOURCE
from capture.openenv_unix_shim import PORT
from capture.relay import ROUTE
from capture.seal import save

from .contracts import PLAN, policy_trial, require, targets
from .harbor_cpu_verifier import require_ok, verify_submission
from .harbor_pack import prepare

PROBE = r"""
import http.client
import json
import os
from pathlib import Path
import socket
import sys

if len(sys.argv) > 2:
    model, route = sys.argv[2:]
    conn = http.client.HTTPConnection("127.0.0.1", int(sys.argv[1]), timeout=4)
    try:
        conn.request("POST", route, json.dumps({"model": model, "stream": True,
                      "messages": [{"role": "user", "content": "Budget exhaustion check."}]}),
                     {"Content-Type": "application/json"})
        r = conn.getresponse()
        assert r.status == 422 and b"engine trial budget exhausted" in r.read()
        print(json.dumps({"status": r.status, "reason": "engine trial budget exhausted"}))
    finally:
        conn.close()
    sys.exit(0)

assert [name for _, name in socket.if_nameindex()] == ["lo"]
assert all(line.split()[0] == "lo" for line in Path("/proc/net/route").read_text().splitlines()[1:] if line)
for path in ("/bridge", "/audit", "/deps", "/var/run/docker.sock", "/work/.aws", "/tests", "/workspace"):
    assert not os.path.lexists(path), path
no_credentials = ("OPENENV_CAPTURE_ADMIN_KEY", "OCA_CAPTURE_SESSION", "HF_TOKEN", "OPENAI_API_KEY",
                  "AWS_SECRET_ACCESS_KEY", "ANTHROPIC_API_KEY", "HTTP_PROXY", "HTTPS_PROXY")
assert not any(key in os.environ for key in no_credentials)
config = json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])
assert config["provider"]["local"]["options"]["apiKey"] == "dummy"
checks = {}
for method, route, expected in [("GET", "/v1/models", 200), ("GET", "/health", 404),
                               ("GET", "/sessions", 404), ("POST", "/sessions", 404)]:
    with_socket = http.client.HTTPConnection("127.0.0.1", int(sys.argv[1]), timeout=4)
    try:
        with_socket.request(method, route, "{}" if method == "POST" else None)
        r = with_socket.getresponse()
        assert r.status == expected, (method, route, r.status)
        checks[method + " " + route] = r.status
    finally:
        with_socket.close()
print(json.dumps({"interfaces": ["lo"], "external_routes": 0, "private_mounts": [],
                  "credential_variables": [], "control_surface": checks}))
"""


@contextmanager
def process(docker, label, runtime, bridge, *, packages=None, audit=None):
    name = docker.name(label)
    args = docker.sandbox(name, memory="512m") + ["-d", "--log-driver=local", "--workdir=/app"]
    args += docker.mount(runtime, "/app/capture") + docker.mount(bridge, "/bridge", writable=packages is not None)
    if packages is not None:
        args += ["--user=0:0", "--cap-add=DAC_OVERRIDE", "--env", "PYTHONPATH=/app:/deps"]
        args += docker.mount(packages, "/deps") + docker.mount(audit, "/audit", writable=True)
    try:
        require_ok(docker.invoke(args + [IMAGE, "python", "-E" if packages is None else "-s",
                                       "-B", "-u", "-m", f"capture.{label}"]), f"start {label}")
        for _ in range(30):
            logs = docker.invoke(["logs", name], timeout=3)
            require_ok(logs, f"check {label}")
            ready = (bridge / "ingress.sock").exists() if packages is not None else "shim-ready" in logs[2]
            if ready:
                break
            if logs[3]:
                raise RuntimeError(f"{label} startup: {logs[3]}")
            time.sleep(0.12)
        else:
            raise RuntimeError(f"{label} startup expired")
        yield name
    finally:
        docker.remove(name)


def check_trace(trace):
    require(trace["source"] == SOURCE and trace["usable_for_grpo"] is False,
            "bad provenance for controlled-engine evidence")
    require(trace["upstream_errors"] == 0 and trace["fixture_http_calls"] == 4,
            "invalid controlled-engine call accounting")
    budget = trace["engine_budget"]
    require(budget["sent_limits"] == budget["received_limits"]
            and budget["sent_limits"] in ([3, 3, 3, 1], [3, 3, 2, 1])
            and budget["output_tokens"] == 6, "live engine budget was not enforced")
    turns = trace["turns"]
    for generated in ([20, 21], [22, 23], [24]):
        require(sum(turn["completion_token_ids"] == generated for turn in turns) == 1,
                "OpenEnv did not export the tool-loop token sequence exactly once")
    edit = next(turn for turn in turns if turn["completion_token_ids"] == [22, 23])
    require(edit["prompt_token_ids"][-2:] == [70, 71]
            and edit["loss_mask"][4:6] == [0, 0]
            and [token for _, token, _ in targets(edit)] == [22, 23], "tool output was included as a loss target")
    try:
        policy_trial(trace, Path("."))
    except ValueError as exc:
        require("need genuine OpenEnv engine capture" in str(exc), "unrelated training rejection")
    else:
        raise RuntimeError("CPU fixture was admitted to training")


def stage_runtime(root):
    root.mkdir()
    root.chmod(0o755)
    for name in ("__init__.py", "openenv_cpu_service.py", "openenv_unix_shim.py", "budget_transport.py",
                 "engine_budget.py", "fixture_engine.py", "relay.py", "trace.py"):
        shutil.copyfile(ROOT / "capture" / name, root / name)
        (root / name).chmod(0o444)


def main():
    from .harbor_trial import run_trial

    require(sys.version_info[:2] == (3, 13), "requires Python 3.13 packages to match the cached container image")
    for key in ("harbor", "openenv"):
        require(version(key) == PLAN["runtime"][key], f"expected {key} {PLAN['runtime'][key]}")
    verify_fixtures()
    require(CLI.is_file(), "preinstall the locked OpenCode; this stage does not download")
    docker = Docker()
    require_ok(docker.invoke(["image", "inspect", IMAGE]), "preflight cached image (no pull)")
    output = ROOT / "artifacts" / ("harbor-openenv-cpu-" + uuid.uuid4().hex[:10])
    output.mkdir(parents=True)
    print(f"Upstream CPU artifacts: {output}", flush=True)
    (output / "cli-verification.txt").write_text(verify_cli(docker), encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="oca-upstream-cpu-") as tmp, ExitStack() as stack:
        root = Path(tmp)
        runtime, bridge, audit = (root / name for name in ("runtime", "bridge", "audit"))
        for path in (bridge, audit):
            path.mkdir()
        stage_runtime(runtime)
        bridge.chmod(0o777)
        audit.chmod(0o777)

        prepare(root / "harbor")
        task = Task(root / "harbor" / "tasks" / "boundary")
        require(task.config.environment.network_mode == "no-network"
                and task.config.verifier.environment_mode == "separate"
                and task.config.verifier.network_mode == "no-network", "Harbor task does not preserve isolation")
        before = task.paths.environment_dir / "solution.py"
        original = read_submission(before)
        baseline = verify_submission(docker, task, before, output / "harbor-original")
        require(baseline["rewards"] == {"correctness": 0}, "Harbor did not reject the unedited task")

        stack.enter_context(process(docker, "openenv_cpu_service", runtime, bridge,
                                    packages=Path(sysconfig.get_paths()["purelib"]), audit=audit))
        shim = stack.enter_context(process(docker, "openenv_unix_shim", runtime, bridge))
        result, paths = asyncio.run(run_trial(
            task=root / "harbor" / "tasks" / task.name, output=output / "trials", shim=shim,
            served_model=MODEL, wall_seconds=45, relay_mode="synthetic"))
        cli = (paths.agent_dir / "cli-events.jsonl").read_text()
        calls = [(row["part"]["tool"], row["part"]["state"]["status"])
                 for row in json_lines(cli) if row["type"] == "tool_use"]
        require(calls == [("read", "completed"), ("edit", "completed")], "missing actual read/edit tool events")

        trace = json.loads((audit / "openenv-trace.json").read_text())
        check_trace(trace)
        save(output / "openenv-trace.json", trace)
        budget_stop = json.loads((paths.agent_dir / "budget-stop.json").read_text())

        final = read_submission(paths.artifacts_dir / "work" / "solution.py")
        record_patch(output, original, final)
        require(final != original, "missing actual patch")
        require(result.verifier_result.rewards == {"correctness": 1},
                "Harbor Trial verifier did not accept the transferred artifact")
    summary = {
        "status": "pass", "source": SOURCE, "usable_for_grpo": False, "gpu_used": False,
        "host_ip_socket_guard": True,
        "real_components": ["OpenCode 2.2.7", "Harbor Trial.create/run, artifact transfer and separate verifier",
                            "OpenEnv capture sessions, trace_entries and TrainingTrace.from_entries"],
        "controlled_components": ["engine replies, token IDs and logprobs", "custom Harbor Docker sandbox provider"],
        "task": task.name, "cli_completed_tools": calls, "openenv_exported_turns": len(trace["turns"]),
        "harbor_trial": str(paths.result_path.relative_to(output)), "harbor_trial_id": str(result.id),
        "verifier_isolation": json.loads((paths.verifier_dir / "isolation.json").read_text()),
        "harbor_rewards": {"original": 0, "edited": 1}, "training_consumer_rejected": True,
        "engine_budget": trace["engine_budget"], "budget_stop": budget_stop,
    }
    save(output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
