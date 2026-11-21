"""Noninteractive CLI execution against private loopback endpoints."""

from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import time

from containers import IMAGE, ROOT
from mock_api import MAX_CALLS as MOCK_MAX_CALLS, MODEL as MOCK_MODEL, PORT
from protocol import LIMITS, PROTOCOL

MODEL = f"local/{MOCK_MODEL}"
AGENT_VERSION = PROTOCOL["cli_version"]
AGENT_TIMEOUT = LIMITS["smoke_wall_s"]
MAX_OUTPUT_TOKENS = LIMITS["output_tokens_configured"]
DEFAULT_PREFIX = ROOT / ".tools" / f"opencode-{AGENT_VERSION}"
CLI = Path(os.environ.get("OPENCODE_PREFIX", DEFAULT_PREFIX)).resolve() / "bin" / "opencode"


@dataclass(frozen=True)
class LocalEndpoint:
    container: str
    model_id: str
    port: int


def pilot_endpoint(docker, container, model_id, port, revision):
    """Require an explicitly selected, isolated container and matching model."""
    if model_id.startswith("scripted-"):
        raise RuntimeError("scripted model IDs are reserved for smoke tests")
    template = "{{.Id}} {{.State.Running}} {{.HostConfig.NetworkMode}} {{.Image}}"
    limit, code, out, _ = docker.invoke(
        ["container", "inspect", "--format", template, "--", container])
    fields = out.strip().split()
    if limit or code or len(fields) != 4:
        raise RuntimeError(f"could not inspect model container {container!r}")
    container_id, running, network, image = fields
    if (running, network) != ("true", "none"):
        raise RuntimeError("model container must be running with --network none")
    endpoint = LocalEndpoint(container_id, model_id, port)

    probe = (ROOT / "harness" / "preflight.py").read_text(encoding="utf-8")
    name = docker.name("probe")
    args = docker.sandbox(name, network=f"container:{endpoint.container}") + ["--log-driver=none"]
    try:
        limit, code, out, err = docker.invoke(args + [
            IMAGE, "python", "-I", "-B", "-c", probe, str(port), model_id, revision,
        ], timeout=12)
    finally:
        docker.remove(name)
    if limit or code:
        raise RuntimeError(f"model endpoint check failed ({limit or code}): {(err or out).strip()}")
    return endpoint, {"container_id": container_id, "container_image_id": image,
                      "network": network, "model_revision": revision,
                      "probe": "GET /v1/models", **json.loads(out)}


@contextmanager
def mock_backend(docker):
    name = docker.name("mock")
    args = docker.sandbox(name) + ["-d", "--log-driver=local"]
    source = (ROOT / "harness" / "mock_api.py").read_text(encoding="utf-8")
    try:
        limit, code, out, err = docker.invoke(args + [IMAGE, "python", "-I", "-B", "-u", "-c", source])
        if limit or code:
            raise RuntimeError(f"mock start failed ({limit or code}): {err or out}")
        for _ in range(40):
            _, _, logs, errors = docker.invoke(["logs", name], timeout=3)
            if '"event": "ready"' in logs:
                yield LocalEndpoint(name, MOCK_MODEL, PORT)
                break
            if errors:
                raise RuntimeError(f"mock startup failed: {errors}")
            time.sleep(0.1)
        else:
            raise RuntimeError("mock did not start on private loopback")
    finally:
        docker.remove(name)


def cli_mount(docker):
    return docker.mount(CLI.resolve(strict=True), "/usr/local/bin/opencode")


def verify_cli(docker):
    name = docker.name("version")
    args = docker.sandbox(name) + ["--log-driver=none", "--env", "HOME=/tmp/opencode-home"]
    try:
        limit, code, out, err = docker.invoke(args + cli_mount(docker) + [
            IMAGE, "sh", "-ec", "opencode --version && opencode run --help",
        ])
    finally:
        docker.remove(name)
    if limit or code or out.splitlines()[:1] != [f"opencode v{AGENT_VERSION}"] or "opencode run [flags]" not in out:
        raise RuntimeError(f"CLI verification failed ({limit or code}): {err or out}")
    return out


def agent_environment(endpoint):
    config = {
        **PROTOCOL["agent_config"],
        "provider": {"local": {
            "npm": "@ai-sdk/openai-compatible",
            "options": {"baseURL": f"http://127.0.0.1:{endpoint.port}/v1", "apiKey": "dummy"},
            "models": {endpoint.model_id: {"tool_call": True,
                                          "limit": {"context": LIMITS["context_tokens_configured"],
                                                    "output": MAX_OUTPUT_TOKENS}}},
        }},
    }
    return ["--env", "HOME=/tmp/opencode-home", "--env", "OPENCODE_DISABLE_MODELS_FETCH=1",
            "--env", "OPENCODE_CONFIG_CONTENT=" + json.dumps(config)]


def agent_command(endpoint, prompt):
    return ["opencode", "run", "--standalone", "--archived", "--format", "json",
            "--model", f"local/{endpoint.model_id}", prompt]


def agent_sandbox(docker, name, work, endpoint):
    args = docker.sandbox(name, network=f"container:{endpoint.container}", memory="768m", cpus="1", pids=128)
    args += ["--log-driver=none", "--workdir", "/work"] + agent_environment(endpoint)
    args += docker.mount(work, "/work", writable=True)
    return args + cli_mount(docker)


def run_agent(docker, work, prompt, endpoint, *, timeout=AGENT_TIMEOUT):
    name = docker.name("agent")
    args = agent_sandbox(docker, name, work, endpoint)
    try:
        return docker.invoke(args + [IMAGE, *agent_command(endpoint, prompt)], timeout=timeout)
    finally:
        docker.remove(name)


def json_lines(output):
    events = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events
