"""Run coding-agent trials (OpenCode / Pi) through CaptureProxy and grade them safely.

Supports `single_file`, `repo_pytest`, and `swe_verified` tasks. On Linux/Colab:
- Tightens per-trial temp workspace permissions to `0700` (preventing cross-trial peeking across
  concurrent workers);
- Automatically wraps harness execution in `bubblewrap (bwrap)` mount/PID/IPC sandbox when supported
  by the host kernel (keeping `/content/runs`, `/content/repo/grader`, and sibling `/tmp/oca-*`
  invisible while still allowing loopback proxy traffic), with transparent fallback to unprivileged
  `agent` UID isolation when container kernels disable user namespaces.
"""
import asyncio
import json
import os
from pathlib import Path
try:
    import pwd
except ImportError:  # Windows host (only unit tests / offline helpers)
    pwd = None
import secrets
import shutil
import signal
import subprocess
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

_BWRAP_OK: bool | None = None


def probe_bwrap() -> bool:
    """Check once whether bubblewrap mount/PID sandboxing works on this Linux kernel."""
    global _BWRAP_OK
    if _BWRAP_OK is not None:
        return _BWRAP_OK
    if os.name == "nt":
        _BWRAP_OK = False
        return False
    bwrap = shutil.which("bwrap")
    if not bwrap:
        _BWRAP_OK = False
        return False
    try:
        p = subprocess.run(
            [bwrap, "--ro-bind", "/", "/", "--proc", "/proc", "--dev", "/dev",
             "--unshare-pid", "--die-with-parent", "/bin/true"],
            capture_output=True, timeout=5,
        )
        _BWRAP_OK = (p.returncode == 0)
    except Exception:
        _BWRAP_OK = False
    return _BWRAP_OK


def build_bwrap_cmd(cmd: list[str], work: Path, home: Path, extra_ro_dirs: list[Path] | None = None) -> list[str]:
    """Construct a bubblewrap command isolating filesystem visibility to system libs + this trial only."""
    bwrap = shutil.which("bwrap") or "bwrap"
    args = [bwrap, "--die-with-parent", "--unshare-pid", "--unshare-ipc"]
    for sys_ro in ("/usr", "/bin", "/lib", "/lib64", "/sbin", "/etc/alternatives", "/etc/ssl", "/etc/ld.so.cache",
                   "/etc/ld.so.conf", "/etc/ld.so.conf.d", "/etc/passwd", "/etc/group", "/etc/hosts", "/etc/resolv.conf"):
        if os.path.exists(sys_ro):
            args += ["--ro-bind", sys_ro, sys_ro]
    # Expose only runtime tools & optional repo venvs read-only (NEVER /content/runs or /content/repo/grader!)
    for tool_ro in ("/content/tools", "/content/swe_venvs", "/opt", "/usr/local"):
        if os.path.exists(tool_ro):
            args += ["--ro-bind", tool_ro, tool_ro]
    for p in extra_ro_dirs or []:
        if p and os.path.exists(p):
            args += ["--ro-bind", str(p), str(p)]
    args += [
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--bind", str(work), str(work),
        "--bind", str(home), str(home),
        "--chdir", str(work),
        "--",
        *cmd,
    ]
    return args


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
    if task.kind in ("repo_pytest", "swe_verified"):
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
    if task.kind in ("repo_pytest", "swe_verified"):
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

    prompt = PROMPT_REPO if task.kind in ("repo_pytest", "swe_verified") else PROMPT_SINGLE
    # Route through an unguessable per-trial nonce so sibling processes cannot hijack another trial's proxy URL
    route_id = f"{trial_id}-{secrets.token_hex(4)}"
    base_url = f"{proxy.base}/t/{route_id}/v1"
    cmd, env = harness.prepare(home, base_url, binary, prompt, cfg)

    # Prepend per-task venv bin dir if present (for SWE-bench Verified / SWE-smith pure-Python repos)
    venv_bin = None
    if getattr(task, "venv_dir", None):
        vb = Path(task.venv_dir) / "bin"
        if vb.is_dir():
            venv_bin = vb
            env["PATH"] = f"{vb}:{env.get('PATH', '/usr/bin:/bin')}"
            env["VIRTUAL_ENV"] = str(task.venv_dir)

    ids = _agent_ids()
    if os.name != "nt":
        os.chmod(root, 0o700)
        if ids:
            for dirpath, _, files in os.walk(root):
                os.chown(dirpath, *ids)
                for f in files:
                    os.chown(os.path.join(dirpath, f), *ids)

    use_bwrap = bool(r.get("use_bwrap", True)) and probe_bwrap()
    sandbox_mode = "bwrap+uid" if (use_bwrap and ids) else ("bwrap" if use_bwrap else ("uid_0700" if ids else "host"))
    exec_cmd = build_bwrap_cmd(cmd, work, home, extra_ro_dirs=[venv_bin.parent] if venv_bin else None) if use_bwrap else cmd

    budget = {"max_model_calls": r["max_model_calls"], "max_output_tokens_per_trial": r["max_output_tokens_per_trial"]}
    safe_intercept = bool(r.get("safe_intercept", False))
    proxy.register(
        route_id, model, seed, budget, aux_mode=harness.aux_mode,
        safe_intercept=safe_intercept, protected_paths=["TASK.md", *protected_tests],
    )

    def demote():
        os.setsid()
        if os.name != "nt":
            try:
                import resource
                resource.setrlimit(resource.RLIMIT_FSIZE, (32 << 20, 32 << 20))
            except (ValueError, OSError):
                pass
        if ids:
            os.setgid(ids[1])
            os.setuid(ids[0])

    started = time.time()
    timed_out = False
    proc = await asyncio.create_subprocess_exec(
        *exec_cmd, cwd=work, env=env,
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
    except asyncio.CancelledError:
        # Cleanly reap child process group on Early-Cutoff straggler cancellation
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            await proc.wait()
        except Exception:
            pass
        proxy.trials.pop(route_id, None)
        if not keep_workdir:
            shutil.rmtree(root, ignore_errors=True)
        raise

    wall = time.time() - started
    trial = proxy.pop(route_id)

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
        "sandbox_mode": sandbox_mode,
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
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # keep the batch alive; failed trials are excluded from training
                rec = {"trial_id": job[3], "task_id": job[0].id, "kind": job[0].kind,
                       "harness": harness_name, "model": job[1], "seed": job[2],
                       "error": repr(exc), "reward": None, "turns": []}
            if on_done:
                on_done(rec)
            return rec

    return await asyncio.gather(*(one(j) for j in jobs))
