"""Harbor's public Trial API with preloaded, isolated local Docker sandboxes."""

import asyncio
from base64 import b64decode
from contextlib import ExitStack
import json
from pathlib import Path
import shlex
import tempfile

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment, ExecResult
from harbor.environments.capabilities import EnvironmentCapabilities, EnvironmentResourceCapabilities
from harbor.models.trial.config import AgentConfig, EnvironmentConfig, TaskConfig, TrialConfig
from harbor.trial.trial import Trial

from agent import AGENT_VERSION, LocalEndpoint, agent_command, agent_environment, cli_mount
from containers import Docker, IMAGE
from grade import read_submission
from capture.relay import ROUTE

from .harbor_cpu_verifier import environment as verifier_environment, require_ok
from .upstream_cpu import MODEL, PORT, PROBE

SOLUTION = "/work/solution.py"
AGENT_LOGS = "/logs/agent"
ARTIFACTS = "/logs/artifacts"
VERIFIER_PROBE = """
import json, os, socket
from pathlib import Path
assert [name for _, name in socket.if_nameindex()] == ['lo']
assert all(line.split()[0] == 'lo' for line in Path('/proc/net/route').read_text().splitlines()[1:] if line)
assert not any(os.path.lexists(path) for path in ('/bridge', '/audit', '/var/run/docker.sock', '/workspace'))
assert not any(key in os.environ for key in ('HF_TOKEN', 'OPENAI_API_KEY', 'AWS_SECRET_ACCESS_KEY',
                                            'OCA_CAPTURE_SESSION', 'OPENCODE_CONFIG_CONTENT'))
Path('/logs/verifier/isolation.json').write_text(json.dumps(
    {'interfaces': ['lo'], 'external_routes': 0, 'private_mounts': [], 'credential_variables': []}) + '\\n')
"""
# Read one bounded regular file as the unprivileged sandbox user. Never follow a symlink or open
# devices on the host, including when a task leaves a background process running.
READ_ARTIFACT = """
import base64, os, stat
fd = os.open('/work/solution.py', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
with os.fdopen(fd, 'rb') as source:
    assert stat.S_ISREG(os.fstat(fd).st_mode), 'invalid artifact type'
    data = source.read(65537)
    assert len(data) <= 65536, 'artifact too large'
print(base64.b64encode(data).decode('ascii'))
"""


class RelaySandbox(BaseEnvironment):
    """A fresh agent sandbox or separate offline verifier for the frozen pilot."""

    capabilities = EnvironmentCapabilities(disable_internet=True)

    @classmethod
    def resource_capabilities(cls):
        return EnvironmentResourceCapabilities(cpu_limit=True, memory_limit=True, fractional_cpus=True)

    @staticmethod
    def type():
        return "oca-local-relay"

    def __init__(self, *args, shim, served_model, **kwargs):
        self.endpoint = LocalEndpoint(shim, served_model, PORT)
        self.docker = Docker()
        self.name = None
        self.verifier = None
        self.received_artifact = False
        self.stack = ExitStack()
        super().__init__(*args, **kwargs)

    def _validate_definition(self):
        if (self.environment_dir.name not in ("environment", "tests")
                or not (self.environment_dir / "Dockerfile").is_file()
                or not self._network_disabled
                or self._host_mounts or self._persistent_env):
            raise ValueError("expected a frozen offline task and no configured host mounts")

    async def start(self, force_build):
        if force_build:
            raise ValueError("trial requires cached images")
        if self.environment_dir.name == "tests":
            stage = self.stack.enter_context(tempfile.TemporaryDirectory(prefix="oca-trial-grade-"))
            self.submission = Path(stage) / "solution.py"
            self.submission.touch(mode=0o600)
            self.verifier = self.stack.enter_context(
                verifier_environment(self.docker, self.environment_dir, self.submission))
            return

        state = await asyncio.to_thread(self.docker.invoke, [
            "container", "inspect", "--format", "{{.HostConfig.NetworkMode}} {{.State.Running}}",
            "--", self.endpoint.container])
        require_ok(state, "inspect relay namespace")
        if state[2].strip() != "none true":
            raise ValueError("relay must use a running Docker no-network namespace")

        self.name = self.docker.name("trial-agent")
        args = self.docker.sandbox(self.name, network=f"container:{self.endpoint.container}",
                                   memory="768m", cpus="1", pids=128)
        args += ["-d", "--log-driver=none", "--workdir=/work",
                 "--tmpfs=/work:rw,nosuid,nodev,size=8m,uid=65534,gid=65534,mode=0700"]
        args += agent_environment(self.endpoint) + cli_mount(self.docker)
        require_ok(await asyncio.to_thread(self.docker.invoke, args + [IMAGE, "sleep", "300"]),
                   "start Harbor agent sandbox")
        seed = read_submission(self.environment_dir / "solution.py").encode("utf-8")
        require_ok(await asyncio.to_thread(self.docker.invoke, [
            "exec", "-i", self.name, "sh", "-c", f"cat > {SOLUTION}"], payload=seed),
            "stage frozen solution")

    async def stop(self, delete):
        if self.name is not None:
            await asyncio.to_thread(self.docker.remove, self.name)
            self.name = None
        await asyncio.to_thread(self.stack.close)

    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
        env = self._merge_env(env)
        user = self._resolve_user(user)
        if env:
            raise ValueError("trial environment overrides are disabled")
        if self.verifier is not None:
            if "/tests/test.sh" in command and not self.received_artifact:
                raise ValueError("Harbor did not transfer the submission to the verifier")
            if user not in (None, "root", 0) or cwd not in (None, "/work"):
                raise ValueError("unexpected verifier user or working directory")
            return await self.verifier.exec(command, user="root")
        if user not in (None, 65534, "65534") or cwd not in (None, "/work"):
            raise ValueError("agent commands must run as the unprivileged task user")
        limit, code, out, err = await asyncio.to_thread(
            self.docker.invoke, ["exec", self.name, "sh", "-c", command],
            timeout=timeout_sec if timeout_sec is not None else 20)
        if limit:
            raise RuntimeError(f"agent command {limit}")
        return ExecResult(return_code=code, stdout=out, stderr=err)

    async def is_dir(self, path, user=None):
        if self.verifier is None and str(path) in (SOLUTION, ARTIFACTS):
            return str(path) == ARTIFACTS
        return await super().is_dir(path, user=user)

    async def ensure_dirs(self, dirs, *, chmod=True):
        if self.verifier is not None and list(map(str, dirs)) == ["/work"]:
            # The immutable path of the single-file mount already exists.
            return ExecResult(return_code=0)
        return await super().ensure_dirs(dirs, chmod=chmod)

    async def empty_dirs(self, dirs, *, chmod=True):
        result = await super().empty_dirs(dirs, chmod=chmod)
        if self.verifier is not None and list(map(str, dirs)) == ["/logs/verifier"]:
            if result is None or result.return_code:
                raise ValueError("Harbor could not reset verifier evidence directory")
            check = await self.exec(shlex.join(["python", "-I", "-c", VERIFIER_PROBE]), user="root")
            if check.return_code:
                raise ValueError("independent verifier isolation check failed")
        return result

    async def download_file(self, source_path, target_path):
        if self.verifier is not None or source_path != SOLUTION:
            raise ValueError("unexpected artifact download path")
        result = await self.exec(shlex.join(["python", "-I", "-c", READ_ARTIFACT]), timeout_sec=5)
        if result.return_code:
            raise ValueError("invalid Harbor submission artifact")
        Path(target_path).write_bytes(b64decode(result.stdout.strip(), validate=True))

    async def upload_file(self, source_path, target_path):
        if self.verifier is None or target_path != SOLUTION or self.received_artifact:
            raise ValueError("unexpected verifier artifact upload")
        # Preserve the bind-mounted inode, which is writable on the trusted host only.
        self.submission.write_text(read_submission(Path(source_path)), encoding="utf-8", newline="")
        self.received_artifact = True

    async def download_dir(self, source_dir, target_dir):
        if self.verifier is not None:
            return await self.verifier.download_dir(source_dir, target_dir)
        if source_dir not in (AGENT_LOGS, ARTIFACTS):
            raise ValueError("unexpected Harbor output directory")
        # Agent stdout and stderr are already written by the host-side adapter; the only
        # task artifact is the explicit file transfer above.

    async def upload_dir(self, source_dir, target_dir):
        if self.verifier is None and target_dir == AGENT_LOGS:
            return
        if self.verifier is not None and target_dir == ARTIFACTS and not any(Path(source_dir).iterdir()):
            return
        raise ValueError("unexpected Harbor directory upload")


class RelayOpenCode(BaseAgent):
    @staticmethod
    def name():
        return "oca-opencode-relay"

    def version(self):
        return AGENT_VERSION

    async def setup(self, environment):
        result = await environment.exec("opencode --version", timeout_sec=10)
        if result.return_code or result.stdout.strip() != f"opencode v{AGENT_VERSION}":
            raise RuntimeError("Harbor agent does not contain the locked OpenCode")
        await self.probe(environment, "isolation.json")

    async def run(self, instruction, environment, context):
        result = await environment.exec(
            shlex.join(["timeout", "-k", "2s", str(self.wall_seconds - 3),
                        *agent_command(environment.endpoint, instruction)]),
            timeout_sec=self.wall_seconds - 0.5)
        (self.logs_dir / "cli-events.jsonl").write_text(result.stdout, encoding="utf-8")
        (self.logs_dir / "cli-stderr.txt").write_text(result.stderr, encoding="utf-8")
        if result.return_code:
            raise RuntimeError(f"OpenCode exited with status {result.return_code}")
        if environment.endpoint.model_id == MODEL:
            await self.probe(environment, "budget-stop.json", MODEL, ROUTE)
        context.metadata = {"opencode_version": AGENT_VERSION, "relay_mode": self.relay_mode}

    def __init__(self, *args, wall_seconds, relay_mode, **kwargs):
        super().__init__(*args, **kwargs)
        self.wall_seconds = wall_seconds
        self.relay_mode = relay_mode

    async def probe(self, environment, filename, *args):
        result = await environment.exec(shlex.join(["python", "-I", "-c", PROBE, str(PORT), *args]),
                                        timeout_sec=6)
        if result.return_code:
            raise RuntimeError(f"Harbor relay {filename} failed: {result.stderr[:500]}")
        data = json.loads(result.stdout)
        (self.logs_dir / filename).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


async def run_trial(*, task, output, shim, served_model, wall_seconds, relay_mode):
    config = TrialConfig(
        task=TaskConfig(path=task), trial_name=task.name, trials_dir=output,
        environment=EnvironmentConfig(import_path="colab.harbor_trial:RelaySandbox",
                                      kwargs={"shim": shim, "served_model": served_model}),
        agent=AgentConfig(import_path="colab.harbor_trial:RelayOpenCode", model_name=served_model,
                          skip_model_parsing=True, override_timeout_sec=wall_seconds,
                          kwargs={"wall_seconds": wall_seconds, "relay_mode": relay_mode}),
    )
    trial = await Trial.create(config)
    result = await trial.run()
    if result.exception_info is not None:
        raise RuntimeError(f"Harbor Trial {task.name} failed, see {trial.paths.result_path}")
    if result.verifier_result is None or result.verifier_result.rewards is None:
        raise RuntimeError(f"Harbor Trial {task.name} returned no independent reward")
    return result, trial.paths
