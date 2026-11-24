"""Run coding-agent trials (OpenCode / Pi) through CaptureProxy and grade them safely.

Supports both `single_file` tasks (TASK.md + solution.py) and multi-file `repo_pytest` tasks
(full repository + visible smoke tests + hidden pytest grader). On Colab (root), drops to an
unprivileged `agent` UID with CPU/RAM/NPROC/FSIZE rlimits so hidden graders (`0700`) remain
unreachable and runaway bash scripts cannot take down the host VM.
"""
import asyncio
import json
import os
from pathlib import Path
try:
    import pwd
except ImportError:  # Windows host (only unit tests / offline helpers)
    pwd = None
import shutil
import signal
import tempfile
import time

from . import CONFIG
from .grade import grade_task
from .harnesses import get_harness
from .harnesses.opencode import opencode_config  # re-export for backwards compatibility
from .reward import compute_reward, hack_flags

PROMPT_SINGLE = (
    "Read TASK.md, then fix solution.py so it satisfies the specification exactly. "
    "Only modify solution.py. You may run Python to check your work. "
    "When you are done, reply with a one-sentence summary."
)
PROMPT_REPO = (
    "Read TASK.md and explore the repository files, then fix the bugs in the source modules so all "
    "requirements pass. Do NOT modify TASK.md or any files under tests/. You may run pytest or Python "
    "to verify your fix. When you are done, reply with a one-sentence summary."
)


def _agent_ids():
    if pwd is None or not hasattr(os, "geteuid") or os.geteuid() != 0:
        return None
    try:
        p = pwd.getpwnam("agent")
        return p.pw_uid, p.pw_gid
    except KeyError:
        return None


def _copy_lf(src: Path, dst: Path):
    """Copy a text file normalizing CRLF -> LF so Linux edit tools always match cleanly."""
    raw = src.read_bytes()
    if b"\x00" not in raw:
        raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    dst.write_bytes(raw)


def _populate_workspace(task, work: Path) -> tuple[dict[str, str], list[str]]:
    """Copy visible task files into `work`; return (original_file_texts, protected_test_paths)."""
    original = {}
    protected = []
    if task.kind == "repo_pytest":
        for root, dirs, files in os.walk(task.task_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache", ".git")]
            rel_dir = Path(root).relative_to(task.task_dir)
            (work / rel_dir).mkdir(parents=True, exist_ok=True)
            for fn in files:
                sp = Path(root) / fn
                if sp.is_symlink():
                    continue
                dp = work / rel_dir / fn
                _copy_lf(sp, dp)
                rel_s = (rel_dir / fn).as_posix()
                if fn == "TASK.md" or fn.endswith(".py"):
                    original[rel_s] = dp.read_text(encoding="utf-8", errors="replace")
                if rel_s.startswith("tests/") and fn.endswith(".py"):
                    protected.append(rel_s)
    else:
        for name in ("TASK.md", "solution.py"):
            _copy_lf(task.task_dir / name, work / name)
            original[name] = (work / name).read_text(encoding="utf-8", errors="replace")
    return original, sorted(protected)


def _collect_final_code(task, work: Path) -> str | None:
    if task.kind == "repo_pytest":
        chunks = []
        for p in sorted(work.rglob("*.py")):
            rel = p.relative_to(work).as_posix()
            if rel.startswith("tests/") or "__pycache__" in p.parts:
                continue
            chunks.append(p.read_text(encoding="utf-8", errors="replace"))
        return "\n".join(chunks) if chunks else None
    sol = work / "solution.py"
    return sol.read_text(encoding="utf-8", errors="replace") if sol.is_file() else None


async def run_trial(proxy, task, model, seed, trial_id, out_dir, cfg=CONFIG,
                    harness_name="opencode", bin_override=None, keep_workdir=False):
    r = cfg["rollout"]
    harness = get_harness(harness_name)
    binary = harness.resolve_bin(cfg, bin_override)
    await harness.warmup(binary, cfg)

    root = Path(tempfile.mkdtemp(prefix=f"oca-{trial_id}-"))
    work, home = root / "repo", root / "home"
    work.mkdir()
    home.mkdir()
    original, protected_tests = _populate_workspace(task, work)

    prompt = PROMPT_REPO if task.kind == "repo_pytest" else PROMPT_SINGLE
    base_url = f"{proxy.base}/t/{trial_id}/v1"
    cmd, env = harness.prepare(home, base_url, binary, prompt, cfg)

    ids = _agent_ids()
    if ids:
        os.chmod(root, 0o755)
        for dirpath, _, files in os.walk(root):
            os.chown(dirpath, *ids)
            for f in files:
                os.chown(os.path.join(dirpath, f), *ids)

    budget = {"max_model_calls": r["max_model_calls"], "max_output_tokens_per_trial": r["max_output_tokens_per_trial"]}
    proxy.register(trial_id, model, seed, budget, aux_mode=harness.aux_mode)

    def demote():
        os.setsid()
        if os.name != "nt":
            try:
                import resource
                # NOTE: Do NOT cap RLIMIT_AS or per-UID RLIMIT_NPROC tightly here:
                # Node.js/Bun (OpenCode/Pi) mmap >4 GiB virtual address space and spawn
                # ~10 threads per worker, so 32 concurrent `agent` trials share one UID.
                # Isolation is enforced by `agent` UID + 0700 hidden graders + timeout killpg
                # + strict per-worker rlimits inside `oca/grade.py`.
                resource.setrlimit(resource.RLIMIT_FSIZE, (32 << 20, 32 << 20))
            except (ValueError, OSError):
                pass
        if ids:
            os.setgid(ids[1])
            os.setuid(ids[0])

    started = time.time()
    timed_out = False
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=work, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        preexec_fn=None if os.name == "nt" else demote,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=r["timeout_seconds"])
    except asyncio.TimeoutError:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, stderr = await proc.communicate()
    wall = time.time() - started
    trial = proxy.pop(trial_id)

    verdict = await asyncio.to_thread(grade_task, task, work, cfg["grade"]["timeout_seconds"])
    final = _collect_final_code(task, work)
    policy_turns = [t for t in trial.turns if not t.get("aux")]
    flags = hack_flags(work, original, final, turns=policy_turns, protected_files=protected_tests)
    reward, parts = compute_reward(verdict, policy_turns, flags, cfg)

    events = []
    for line in stdout.decode(errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    record = {
        "trial_id": trial_id, "task_id": task.id, "split": task.split,
        "kind": task.kind, "domain": task.domain, "harness": harness.name,
        "model": model, "seed": seed,
        "reward": reward, "reward_parts": parts, "grade": {k: v for k, v in verdict.items() if k != "stderr"},
        "hack_flags": flags, "timed_out": timed_out, "exit_code": proc.returncode, "wall_s": round(wall, 2),
        "budget_exhausted": trial.exhausted, "n_calls": trial.calls, "n_policy_turns": len(policy_turns),
        "completion_tokens": trial.completion_tokens,
        "capture_ok": all(t.get("capture_ok") for t in policy_turns) and bool(policy_turns),
        "tool_calls": [c["function"]["name"] for t in policy_turns for c in (t.get("message") or {}).get("tool_calls") or []],
        "final_solution": final[:16000] if isinstance(final, str) else None,
        "stderr_tail": stderr.decode(errors="replace")[-3000:],
        "n_events": len(events),
        "turns": trial.turns,
        "last_request_messages": trial.last_request_messages,
    }
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{trial_id}.json").write_text(json.dumps(record), encoding="utf-8")
    if not keep_workdir:
        shutil.rmtree(root, ignore_errors=True)
    return record


async def run_batch(proxy, jobs, out_dir, concurrency=None, cfg=CONFIG, on_done=None, harness_name="opencode"):
    """jobs: list of (task, model, seed, trial_id). Returns records in job order."""
    sem = asyncio.Semaphore(concurrency or cfg["rollout"]["concurrency"])

    async def one(job):
        async with sem:
            try:
                rec = await run_trial(proxy, *job, out_dir=out_dir, cfg=cfg, harness_name=harness_name)
            except Exception as exc:  # keep the batch alive; failed trials are excluded from training
                rec = {"trial_id": job[3], "task_id": job[0].id, "kind": job[0].kind,
                       "harness": harness_name, "model": job[1], "seed": job[2],
                       "error": repr(exc), "reward": None, "turns": []}
            if on_done:
                on_done(rec)
            return rec

    return await asyncio.gather(*(one(j) for j in jobs))
