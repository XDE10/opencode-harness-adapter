"""Run one hardware acceptance trial using an explicitly authorized existing G4."""

import argparse
import asyncio
from contextlib import ExitStack, asynccontextmanager, suppress
import json
import logging
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
from importlib.metadata import version

from agent import CLI, json_lines, verify_cli
from containers import Docker, IMAGE
from grade import read_submission
from run import record_patch
from capture.seal import save
from protocol import verify_fixtures

from .contracts import MODEL, PLAN, PLAN_PATH, ROLLOUT, digest, require, trace_segments, verify_snapshot
from .workflow import serve_arguments

SOURCE = "g4_engine_candidate"
ENGINE_URL = "http://127.0.0.1:8000"
STARTUP_LIMIT = 600


def gpu_sample():
    output = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=uuid,name,memory.total,memory.used", "--format=csv,noheader,nounits"],
        text=True, timeout=4)
    rows = output.strip().splitlines()
    require(len(rows) == 1, "expected one existing GPU")
    uuid, name, total, used = (item.strip() for item in rows[0].split(","))
    require("RTX PRO 6000" in name and int(total) * 1048576 >= PLAN["runtime"]["minimum_vram_bytes"],
            "expected the locked G4-class Blackwell GPU with at least 90 GB visible")
    return uuid, int(used) * 1048576


async def monitored(operation, engine, device, peak):
    task = asyncio.create_task(operation)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=1)
            same_device, used = await asyncio.to_thread(gpu_sample)
            peak[0] = max(peak[0], used)
            require(same_device == device and peak[0] < PLAN["runtime"]["peak_stop_bytes"],
                    "G4 identity changed or the 86 GB stop threshold was reached")
            require(engine.poll() is None, "vLLM exited, see vllm.log")
            if done:
                return task.result()
    except BaseException:
        with suppress(ProcessLookupError):
            os.killpg(engine.pid, signal.SIGTERM)
        raise
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def wait_ready(client, snapshot):
    import httpx

    async with asyncio.timeout(STARTUP_LIMIT):
        while True:
            try:
                reply = await client.get(ENGINE_URL + "/v1/models")
            except httpx.HTTPError:
                await asyncio.sleep(1)
                continue
            if reply.is_success:
                rows = reply.json()["data"]
                require(len(rows) == 1 and rows[0]["id"] == MODEL["id"]
                        and Path(rows[0]["root"]).resolve() == snapshot,
                        "vLLM model listing does not match the verified local snapshot")
                return
            await asyncio.sleep(1)


@asynccontextmanager
async def no_fixture():
    yield


async def first_trial(args, root, docker, peak, device):
    import httpx
    import uvicorn
    from capture.engine_budget import EngineBudget
    from capture.openenv_cpu_service import ingress_app
    from capture.trace import validate_turn
    from openenv.core.harness import TrainingTrace
    from .harbor_pack import prepare
    from .harbor_trial import run_trial
    from .upstream_cpu import process, stage_runtime

    task = root / "harbor" / "tasks" / "boundary"
    prepare(task.parents[1])
    runtime, bridge = root / "runtime", root / "bridge"
    stage_runtime(runtime)
    bridge.mkdir()
    bridge.chmod(0o755)
    sock = bridge / "ingress.sock"
    budget = EngineBudget(max_calls=ROLLOUT["max_model_calls"], per_call=ROLLOUT["max_output_tokens_per_call"],
                          per_trial=ROLLOUT["max_output_tokens_per_trial"])
    tool_turn_seen = False

    def record(data, status, _):
        nonlocal tool_turn_seen
        require(status["upstream_errors"] == 0, "OpenEnv reported an upstream error")
        trace = TrainingTrace.from_entries(data["entries"])
        turns = [turn.model_dump(include={"node_id", "prompt_token_ids", "completion_token_ids",
                                        "per_token_logps", "loss_mask"}) for turn in trace.turns]
        for turn in turns:
            validate_turn(turn)
        tool_turn_seen = any(message.get("role") == "tool" for turn in trace.turns
                             for message in turn.request.get("messages", []))
        staging = args.output / ".trace.tmp"
        save(staging, {"schema_version": 1, "turns": turns, "source": SOURCE, "usable_for_grpo": False})
        staging.replace(args.output / "openenv-candidate-trace.json")

    sampling = {key: ROLLOUT[key] for key in ("temperature", "top_p", "top_k", "min_p",
                           "frequency_penalty", "presence_penalty", "repetition_penalty")}
    app = ingress_app(backend_url=ENGINE_URL, provider="vllm", served_model=MODEL["id"], budget=budget,
                      record=record, source=SOURCE, sampling=sampling, backend_lifespan=no_fixture)
    logging.getLogger("intercept").disabled = True
    server = uvicorn.Server(uvicorn.Config(app, uds=str(sock), access_log=False, log_level="warning",
                                           timeout_graceful_shutdown=3))

    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(root),
           "HF_HOME": str(root / "hf"), "XDG_CACHE_HOME": str(root / "cache"),
           "CUDA_VISIBLE_DEVICES": device, "VLLM_NO_USAGE_STATS": "1", "HF_HUB_OFFLINE": "1",
           "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
    command = [str(args.vllm), *serve_arguments(args.snapshot)[1:]]
    # The serving process is ours to stop. An occupied port aborts before launch.
    with socket.socket() as check:
        check.bind(("127.0.0.1", 8000))
    with (args.output / "vllm.log").open("w") as log, ExitStack() as stack:
        engine = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                  start_new_session=True)
        server_task = None
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=3) as client:
                await monitored(wait_ready(client, args.snapshot), engine, device, peak)
            server_task = asyncio.create_task(server.serve())
            async with asyncio.timeout(8):
                while not server.started or not sock.is_socket():
                    if server_task.done():
                        server_task.result()
                        raise RuntimeError("trusted Unix capture ingress exited")
                    await asyncio.sleep(0.1)
            shim = stack.enter_context(process(docker, "openenv_unix_shim", runtime, bridge))
            async with asyncio.timeout(60 + ROLLOUT["timeout_seconds"]):
                result, paths = await monitored(run_trial(
                    task=task, output=args.output / "trials", shim=shim, served_model=MODEL["id"],
                    wall_seconds=ROLLOUT["timeout_seconds"], relay_mode=SOURCE), engine, device, peak)
        finally:
            with suppress(ProcessLookupError):
                os.killpg(engine.pid, signal.SIGTERM)
            try:
                await asyncio.to_thread(engine.wait, 5)
            except subprocess.TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(engine.pid, signal.SIGKILL)
                await asyncio.to_thread(engine.wait, 5)
            if server_task is not None:
                server.should_exit = True
                await server_task

    events = json_lines((paths.agent_dir / "cli-events.jsonl").read_text())
    tools = [event["part"]["tool"] for event in events if event["type"] == "tool_use"
             and event["part"]["state"]["status"] == "completed"]
    trace_path = args.output / "openenv-candidate-trace.json"
    turns = json.loads(trace_path.read_text())["turns"]
    require(tools and tool_turn_seen and any(any(turn["loss_mask"]) for turn in turns)
            and not budget.failed and budget.pending is None,
            "need an observed completed tool roundtrip and valid masked engine trace")
    reward = result.verifier_result.rewards["correctness"]
    require(reward in (0, 1), "missing binary independent reward")
    final = read_submission(paths.artifacts_dir / "work" / "solution.py")
    record_patch(args.output, read_submission(task / "environment" / "solution.py"), final)
    return {"status": "passed_candidate", "source": SOURCE, "usable_for_grpo": False,
            "model": MODEL["id"], "revision": MODEL["revision"], "protocol_sha256": digest(PLAN_PATH),
            "opencode_version": PLAN["runtime"]["opencode"], "tool_parser": PLAN["runtime"]["vllm_tool_parser"],
            "trial": str(paths.result_path.relative_to(args.output)), "correctness": reward,
            "tool_calls": tools, "model_calls": len(budget.sent_limits), "output_tokens": budget.output_tokens,
            "trace_sha256": digest(trace_path), "segments": trace_segments(turns)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--vllm", type=Path, required=True)
    parser.add_argument("--allow-existing-g4", action="store_true")
    args = parser.parse_args()
    if not args.allow_existing_g4:
        parser.error("requires explicit --allow-existing-g4")
    require(all(path.is_absolute() for path in (args.snapshot, args.output, args.vllm)),
            "use absolute local paths")
    require(args.vllm.is_file() and os.access(args.vllm, os.X_OK), "need the installed vLLM executable")
    for name in ("harbor", "openenv"):
        require(version(name) == PLAN["runtime"][name], f"need pinned {name}")
    args.snapshot = args.snapshot.resolve(strict=True)
    verify_snapshot(args.snapshot)
    verify_fixtures()
    require(CLI.is_file(), "need cached OpenCode")
    docker = Docker()
    from .harbor_cpu_verifier import require_ok
    require_ok(docker.invoke(["image", "inspect", IMAGE]), "preflight cached Docker image")
    args.output.mkdir(mode=0o700)
    (args.output / "cli-verification.txt").write_text(verify_cli(docker))
    device, used = gpu_sample()
    compute = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"],
                                      text=True, timeout=4).strip()
    require(not compute and used < 2 * 1024 ** 3, "the authorized G4 is not idle")
    peak = [used]
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="oca-g4-") as directory:
        summary = asyncio.run(first_trial(args, Path(directory), docker, peak, device))
    summary.update(peak_vram_bytes=peak[0], elapsed_seconds=time.monotonic() - started)
    save(args.output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
