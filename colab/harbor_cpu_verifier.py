"""Offline Docker transport for Harbor's pinned Verifier API."""

import asyncio
from contextlib import contextmanager
from pathlib import Path

from harbor.environments.base import ExecResult
from harbor.models.task.config import TaskOS
from harbor.models.trial.paths import TrialPaths
from harbor.verifier.verifier import Verifier

from containers import IMAGE


class OfflineVerifierEnvironment:
    """Only the local operations used by the prepackaged Harbor verifier."""

    os = TaskOS.LINUX

    def __init__(self, docker, name):
        self.docker, self.name = docker, name

    def is_path_mounted(self, *_):
        return False

    async def exec(self, command, *, env=None, user=None):
        if env or user not in (None, "root"):
            raise RuntimeError("verifier environment injection and user overrides are disabled")
        limit, code, out, err = await asyncio.to_thread(
            self.docker.invoke, ["exec", "--user", "0:0", self.name, "sh", "-c", command], timeout=15)
        if limit:
            raise RuntimeError(f"verifier command: {limit}")
        return ExecResult(return_code=code, stdout=out, stderr=err)

    async def download_dir(self, source_dir, target_dir):
        if source_dir != "/logs/verifier":
            raise RuntimeError("unexpected verifier output path")
        # The cloud Docker daemon does not expose the guest's tmpfs through docker cp.
        # Read only the known text files from inside the verifier instead.
        for filename in ("reward.json", "reward.txt", "oca-grade.json", "test-stdout.txt", "isolation.json"):
            limit, code, out, err = await asyncio.to_thread(
                self.docker.invoke, ["exec", "--user", "0:0", self.name, "cat", f"{source_dir}/{filename}"])
            if limit or (code and "No such file" not in err):
                raise RuntimeError(f"verifier output collection failed: {limit or err}")
            if code == 0:
                (Path(target_dir) / filename).write_text(out, encoding="utf-8")


def require_ok(result, stage):
    limit, code, out, err = result
    if limit or code:
        raise RuntimeError(f"{stage} failed ({limit or code}): {err or out}")


@contextmanager
def environment(docker, tests, submission):
    name = docker.name("upstream-verifier")
    args = docker.sandbox(name) + ["-d", "--user=0:0", "--cap-add=DAC_OVERRIDE", "--cap-add=SETUID",
                                  "--cap-add=SETGID", "--cap-add=KILL", "--tmpfs=/logs:rw,nosuid,nodev,size=8m",
                                  "--tmpfs=/tests:rw,exec,nosuid,nodev,size=8m", "--log-driver=none"]
    args += docker.mount(tests, "/prepared-tests") + docker.mount(submission, "/work/solution.py")
    try:
        require_ok(docker.invoke(args + [IMAGE, "sleep", "120"]), "start isolated verifier")
        require_ok(docker.invoke(["exec", name, "sh", "-ec",
                    "cp -R /prepared-tests/. /tests/ && chmod 700 /tests && mkdir -p -m 700 /logs/verifier"]),
                   "stage verifier tests")
        yield OfflineVerifierEnvironment(docker, name)
    finally:
        docker.remove(name)


def verify_submission(docker, task, submission, output):
    path = TrialPaths(Path(output))
    path.mkdir()
    with environment(docker, task.paths.tests_dir, submission) as env:
        # Test files were already provided through the independent verifier image/bind path.
        verifier = Verifier(task, path, env, skip_tests_upload=True)
        return asyncio.run(verifier.verify()).model_dump(mode="json")
