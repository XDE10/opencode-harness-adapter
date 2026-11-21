"""Export the frozen pilot as three Harbor task bundles."""

import json
from pathlib import Path
import shutil

from protocol import PROTOCOL, verify_fixtures
from .contracts import PILOT, PLAN, ROOT, ROLLOUT

AGENT_IMAGE = "oca-opencode-runtime:2.2.7"


def prepare(destination):
    verify_fixtures()
    destination.mkdir(parents=True, exist_ok=False)
    image = PROTOCOL["image"]
    (destination / "runtime.Dockerfile").write_text(
        f"FROM {image}\nCOPY --chmod=0755 opencode /usr/local/bin/opencode\n"
        f'RUN [ "$(opencode --version)" = "opencode v{PLAN["runtime"]["opencode"]}" ]\n')
    for task in PILOT:
        root = destination / "tasks" / task
        env, tests = root / "environment", root / "tests"
        env.mkdir(parents=True)
        tests.mkdir()
        shutil.copyfile(ROOT / "tasks" / task / "TASK.md", root / "instruction.md")
        shutil.copyfile(ROOT / "tasks" / task / "solution.py", env / "solution.py")
        (env / "Dockerfile").write_text(
            f"FROM {AGENT_IMAGE}\nWORKDIR /work\nCOPY --chown=65534:65534 solution.py .\n"
            "RUN chown 65534:65534 /work\nUSER 65534:65534\n")
        for file in (ROOT / "grader" / task / "cases.json", ROOT / "harness" / "worker.py",
                     ROOT / "harness" / "verdict.py", ROOT / "colab" / "harbor_verifier.py"):
            shutil.copyfile(file, tests / file.name)
        (tests / "Dockerfile").write_text(
            f"FROM {image}\nWORKDIR /work\nCOPY . /tests/\nRUN chmod 0700 /tests\n")
        wrapper = tests / "test.sh"
        wrapper.write_text("#!/bin/sh\nset -eu\ncd /tests\nexec python -E -s -B /tests/harbor_verifier.py\n")
        wrapper.chmod(0o755)
        (root / "task.toml").write_text(
            'artifacts = ["/work/solution.py"]\n\n'
            '[environment]\nnetwork_mode = "no-network"\ncpus = 1\nmemory_mb = 768\nworkdir = "/work"\n\n'
            f'[agent]\ntimeout_sec = {ROLLOUT["timeout_seconds"]}\nuser = 65534\n\n'
            '[verifier]\nenvironment_mode = "separate"\nnetwork_mode = "no-network"\nuser = 0\ntimeout_sec = 15\n')
    (destination / "prepared.json").write_text(json.dumps({
        "tasks": PILOT, "agent_image_to_build": AGENT_IMAGE,
        "status": "offline_preparation", "capture_route": "pending_credential_free_isolated_relay",
    }, indent=2) + "\n")
