"""End-to-end G4 verification:
1. Unpack /content/oca_repo.tar.gz -> /content/repo
2. Run 3 real OpenCode CLI 2.2.7 pilot trials (`boundary`, `parsing`, `serialization`) through
   `oca.proxy` -> `vLLM Qwen3-8B`, recording first-turn prompt token count, tool calls, and hidden grades.
3. Run 1 real colocated GRPO step (`oca.train --mode train --steps 1 --tasks-per-step 4 --group-size 4`)
   to verify: sleep(level=1) -> PyTorch backward -> non-zero LoRA update -> wake_up -> runtime LoRA hot-swap!
"""
import asyncio, json, os, subprocess, sys, tarfile, time
from pathlib import Path

os.makedirs("/content/repo", exist_ok=True)
with tarfile.open("/content/oca_repo.tar.gz", "r:gz") as tf:
    tf.extractall("/content/repo", filter="data")

if os.environ.get("OCA_STANDALONE") != "1":
    env = {**os.environ, "OCA_STANDALONE": "1", "PYTHONPATH": "/content/repo"}
    p = subprocess.Popen([sys.executable, "-u", "/content/repo/oca/colab/smoke_e2e.py"],
                         cwd="/content/repo", env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in p.stdout:
        print(line, end="", flush=True)
    rc = p.wait()
    if rc != 0:
        raise RuntimeError(f"smoke_e2e standalone exited with {rc}")
    raise SystemExit(0)

sys.path.insert(0, "/content/repo")
os.chdir("/content/repo")

from oca import CONFIG
from oca.proxy import CaptureProxy
from oca.rollout import run_batch
from oca.tasks import by_id
from oca.train import ensure_vllm_running, lock_grader_permissions, vllm_http


async def pilot_smoke():
    lock_grader_permissions()
    ensure_vllm_running("http://127.0.0.1:8000", CONFIG, Path("/content/vllm.log"))
    st, models = vllm_http("http://127.0.0.1:8000", "/v1/models")
    print("vLLM models:", models, flush=True)

    tasks = [by_id()[k] for k in ("boundary", "parsing", "serialization", "sorted-interval")]
    out_dir = Path("/content/runs/pilot_smoke")
    proxy = await CaptureProxy("http://127.0.0.1:8000", CONFIG["rollout"]).start(port=8101)
    jobs = [(t, CONFIG["model"]["served_name"], 2026 + i, f"pilot-{t.id}") for i, t in enumerate(tasks)]
    t0 = time.time()
    recs = await run_batch(proxy, jobs, out_dir, concurrency=4, cfg=CONFIG)
    await proxy.close()

    summary = []
    for r in recs:
        pturns = [t for t in r.get("turns", []) if not t.get("aux")]
        first_prompt_toks = len(pturns[0]["prompt_token_ids"]) if pturns else 0
        summary.append({
            "task": r["task_id"],
            "status": (r.get("grade") or {}).get("status"),
            "reward": r.get("reward"),
            "first_turn_prompt_tokens": first_prompt_toks,
            "n_policy_turns": r.get("n_policy_turns"),
            "completion_tokens": r.get("completion_tokens"),
            "tool_calls": r.get("tool_calls"),
            "capture_ok": r.get("capture_ok"),
            "wall_s": r.get("wall_s"),
            "exit_code": r.get("exit_code"),
        })
    print("\n=== PILOT ROLLOUT SUMMARY ===", flush=True)
    print(json.dumps({"elapsed_s": round(time.time() - t0, 2), "trials": summary}, indent=2), flush=True)
    (out_dir / "pilot_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


subprocess.run(["uv", "pip", "uninstall", "--system", "-q", "torchao"], check=False)

if not Path("/content/runs/pilot_smoke/pilot_summary.json").is_file():
    asyncio.run(pilot_smoke())
else:
    print("Pilot smoke already passed; proceeding to 1-step colocated GRPO + hot-swap.", flush=True)

# Now run 1 colocated GRPO step on v3 train tasks to verify sleep + backward + LoRA hot-swap!
print("\n=== RUNNING 1-STEP COLOCATED GRPO + LORA HOTSWAP SMOKE ===", flush=True)
rc = subprocess.call([
    sys.executable, "-u", "-m", "oca.train",
    "--mode", "train",
    "--out-dir", "/content/runs/smoke_grpo_1step",
    "--steps", "1",
    "--tasks-per-step", "4",
    "--group-size", "4",
    "--concurrency", "16",
    "--no-resume",
])
if rc != 0:
    raise SystemExit(f"1-step smoke train exited with {rc}")
print("\n=== STEP 1 METRICS ===", flush=True)
print(Path("/content/runs/smoke_grpo_1step/checkpoints/step_001/step_metrics.json").read_text(), flush=True)
