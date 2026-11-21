"""Exercise generated Harbor verifier packages without Harbor or GPU."""

import json

from containers import Docker, IMAGE
from .contracts import PILOT, ROOT, require


def verify_pack(bundle):
    docker = Docker()
    docker.prepare()
    checks = {}
    for task in PILOT:
        tests = bundle / "tasks" / task / "tests"
        tests.chmod(0o700)
        for variant, source, expected in (
            ("original", ROOT / "tasks" / task / "solution.py", 0),
            ("reference", ROOT / "grader" / task / "reference.py", 1),
            ("partial", ROOT / "grader" / task / "partial.py", 0),
        ):
            name = docker.name("harbor-verifier")
            # The CPU check bind-mounts the fixture with its host UID.
            args = docker.sandbox(name) + ["--user=0:0", "--cap-add=SETUID", "--cap-add=SETGID", "--cap-add=KILL",
                                          "--cap-add=DAC_OVERRIDE",
                                          "--tmpfs=/logs:rw,nosuid,nodev,size=8m", "--log-driver=none"]
            args += docker.mount(tests, "/tests") + docker.mount(source, "/work/solution.py")
            try:
                limit, code, out, err = docker.invoke(args + [
                    IMAGE, "sh", "-ec", "/tests/test.sh && cat /logs/verifier/reward.json",
                ])
            finally:
                docker.remove(name)
            require(not limit and code == 0, f"{task}/{variant}: verifier failed: {err or out}")
            score = json.loads(out)["correctness"]
            require(score == expected, f"{task}/{variant}: expected reward {expected}, got {score}")
            checks[f"{task}/{variant}"] = score
    return checks
