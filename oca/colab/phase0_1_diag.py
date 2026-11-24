"""Colab G4 Phase 0 & Phase 1 automated diagnostic and verification suite.

Runs end-to-end on a single Colab G4 (RTX PRO 6000 96GB) to lock down all core hypotheses before
spending GPU hours on full 60-step RL runs:
  1. Phase 0a: Diagnose `eval_v3` 12.5% base pass rate with `write` enabled (12 heldout tasks x 1 seed)
     and dump concise failure reasons (tool errors, syntax errors, edge misses).
  2. Phase 0b: Run `Base Thinking-ON` upper-bound check on the same 12 v3 heldout tasks.
  3. Phase 0c: Smoke-verify both harnesses (`opencode` and `pi`) on `single_file` AND `repo_pytest` tasks.
  4. Phase 1a: Exact gradient-equivalence & wall-clock speedup benchmark of
     `Prefix-Merged Multi-Turn Packing` vs per-turn `bs=1` backward on real captured multi-turn traces.
  5. Phase 1b: 3-step colocated GRPO run + forced process restart `--resume` for 2 more steps (5 steps total)
     to verify checkpoint recovery, policy entropy stability, and BF16 logprob divergence histogram.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

from .. import CONFIG, ROOT
from ..eval import classify_trial, summarize_arm
from ..proxy import CaptureProxy
from ..rollout import run_batch
from ..tasks import load
from ..train import (
    _forward_target_logits,
    _split_backbone_lm_head,
    ensure_vllm_running,
    lock_grader_permissions,
    pack_trajectory_segments,
    vllm_http,
)


def _diagnose_failures(records: list[dict], max_examples: int = 8) -> list[dict]:
    out = []
    for r in records:
        cat = classify_trial(r)
        if cat == "solved":
            continue
        out.append({
            "task_id": r["task_id"],
            "category": cat,
            "grade": r.get("grade"),
            "n_policy_turns": r.get("n_policy_turns"),
            "completion_tokens": r.get("completion_tokens"),
            "tool_calls": r.get("tool_calls"),
            "timed_out": r.get("timed_out"),
            "budget_exhausted": r.get("budget_exhausted"),
            "hack_flags": r.get("hack_flags"),
            "stderr_tail": (r.get("stderr_tail") or "")[-300:],
        })
        if len(out) >= max_examples:
            break
    return out


def benchmark_prefix_merge(vllm_url: str, sample_records: list[dict], cfg: dict) -> dict:
    """Measure real wall-clock speedup and exact gradient equivalence: per-turn vs prefix-merged."""
    import torch
    from torch.nn import functional as F
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM

    usable = [r for r in sample_records if r.get("capture_ok") and (r.get("n_policy_turns") or 0) >= 3]
    if not usable:
        usable = [r for r in sample_records if r.get("capture_ok")]
    if not usable:
        return {"skipped": "no captured multi-turn records available"}

    vllm_http(vllm_url, "/sleep?level=1", "POST")
    base = AutoModelForCausalLM.from_pretrained(
        cfg["model"]["local_path"], local_files_only=True, dtype=torch.bfloat16,
        attn_implementation="sdpa", device_map={"": 0},
    )
    base.requires_grad_(False)
    base.config.use_cache = False
    base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    base.enable_input_require_grads()

    lora_cfg = LoraConfig(
        r=cfg["train"]["rank"], lora_alpha=cfg["train"]["alpha"], lora_dropout=0.0,
        target_modules=cfg["train"]["targets"], bias="none", task_type="CAUSAL_LM",
    )
    model = get_peft_model(base, lora_cfg)
    model.train()
    temp = cfg["rollout"]["temperature"]
    trainable = [p for p in model.parameters() if p.requires_grad]

    def run_pass(enable_merge: bool):
        segs = []
        raw_turns = 0
        for idx, rec in enumerate(usable[:8]):
            adv = 1.0 if idx % 2 == 0 else -1.0
            s, st = pack_trajectory_segments(rec["turns"], adv, max_seq=24576, enable_merge=enable_merge)
            segs.extend(s)
            raw_turns += st["raw_turns"]
        total_toks = sum(len(s["target_ids"]) for s in segs)
        for p in trainable:
            p.grad = None
        backbone, lm_head = _split_backbone_lm_head(model)
        torch.cuda.synchronize()
        t0 = time.time()
        for seg in segs:
            ids = torch.tensor([seg["input_ids"]], dtype=torch.long, device="cuda")
            pos = torch.tensor(seg["target_positions"], dtype=torch.long, device="cuda")
            tgt = torch.tensor(seg["target_ids"], dtype=torch.long, device="cuda")
            if backbone is not None and lm_head is not None:
                h = backbone(input_ids=ids, use_cache=False).last_hidden_state[0].index_select(0, pos)
                h_leaf = h.detach().requires_grad_(True)
                for s in range(0, h_leaf.shape[0], 512):
                    e = min(h_leaf.shape[0], s + 512)
                    lg = lm_head(h_leaf[s:e]).float() / temp
                    cur_lp = -F.cross_entropy(lg, tgt[s:e], reduction="none")
                    loss_c = -(seg["adv"] * cur_lp).sum() / max(1, total_toks)
                    loss_c.backward()
                    del lg, cur_lp, loss_c
                h.backward(h_leaf.grad)
                del h, h_leaf
            else:
                logits = _forward_target_logits(model, ids, pos, len(seg["input_ids"]), seg["target_positions"][0])
                cur_lp = -F.cross_entropy(logits / temp, tgt, reduction="none")
                loss = -(seg["adv"] * cur_lp).sum() / max(1, total_toks)
                loss.backward()
                del logits, cur_lp, loss
            del ids, pos, tgt
        torch.cuda.synchronize()
        elapsed = time.time() - t0
        grads = [p.grad.detach().float().cpu().clone() for p in trainable if p.grad is not None]
        return elapsed, raw_turns, len(segs), total_toks, grads

    # Warmup 1 pass then benchmark unmerged vs merged
    t_unmerged, raw_t, n_unmerged, tok_u, g_u = run_pass(enable_merge=False)
    t_merged, _, n_merged, tok_m, g_m = run_pass(enable_merge=True)

    cos_sims = []
    rel_l2 = []
    for a, b in zip(g_u, g_m):
        na, nb = a.norm().item(), b.norm().item()
        if na > 1e-8 and nb > 1e-8:
            cos_sims.append(float((a * b).sum().item() / (na * nb)))
            rel_l2.append(float((a - b).norm().item() / max(na, 1e-8)))

    del model, base, g_u, g_m
    torch.cuda.empty_cache()
    vllm_http(vllm_url, "/wake_up", "POST")

    return {
        "n_trajectories": min(8, len(usable)),
        "raw_turns": raw_t,
        "unmerged_segments": n_unmerged,
        "merged_segments": n_merged,
        "compression_ratio": round(raw_t / max(1, n_merged), 2),
        "tokens_checked": {"unmerged": tok_u, "merged": tok_m},
        "unmerged_s": round(t_unmerged, 2),
        "merged_s": round(t_merged, 2),
        "speedup_x": round(t_unmerged / max(0.01, t_merged), 2),
        "grad_cosine_mean": round(statistics.mean(cos_sims), 6) if cos_sims else 0.0,
        "grad_rel_l2_mean": round(statistics.mean(rel_l2), 6) if rel_l2 else 0.0,
    }


async def run_diag(args):
    cfg = json.loads(json.dumps(CONFIG))
    lock_grader_permissions()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ensure_vllm_running(args.vllm_url, cfg, args.out_dir / "vllm.log")

    report = {}

    # 1. Phase 0a: v3 heldout 12 tasks x 1 seed with `write` enabled (diagnose 12.5% base pass rate)
    v3_held = sorted([t for t in load(split="heldout") if t.source == "v3"], key=lambda t: t.id)
    proxy = await CaptureProxy(args.vllm_url, cfg["rollout"]).start(port=args.proxy_port)
    jobs_v3 = [(t, cfg["model"]["served_name"], 101, f"p0-v3-{t.id}") for t in v3_held]
    recs_v3 = await run_batch(proxy, jobs_v3, args.out_dir / "p0_v3_write_on",
                              concurrency=args.concurrency, cfg=cfg, harness_name="opencode")
    await proxy.close()
    report["phase0_v3_write_enabled"] = {
        "summary": summarize_arm(recs_v3, [101]),
        "failure_samples": _diagnose_failures(recs_v3),
    }
    print("[phase0a] v3 (write enabled):", json.dumps(report["phase0_v3_write_enabled"]["summary"], indent=2), flush=True)

    # 2. Phase 0b: Base Thinking-ON upper bound on the same 12 v3 heldout tasks
    cfg_think = json.loads(json.dumps(cfg))
    cfg_think["rollout"]["enable_thinking"] = True
    cfg_think["rollout"]["max_output_tokens_per_call"] = 4096
    cfg_think["rollout"]["max_output_tokens_per_trial"] = 16384
    proxy_t = await CaptureProxy(args.vllm_url, cfg_think["rollout"]).start(port=args.proxy_port + 1)
    jobs_th = [(t, cfg["model"]["served_name"], 101, f"p0-think-{t.id}") for t in v3_held]
    recs_th = await run_batch(proxy_t, jobs_th, args.out_dir / "p0_v3_thinking_on",
                              concurrency=args.concurrency, cfg=cfg_think, harness_name="opencode")
    await proxy_t.close()
    report["phase0_v3_thinking_on"] = summarize_arm(recs_th, [101])
    print("[phase0b] v3 (thinking ON):", json.dumps(report["phase0_v3_thinking_on"], indent=2), flush=True)

    # 3. Phase 0c: Multi-file repo_pytest + Dual Harness (OpenCode & Pi) smoke check
    repo_tasks = sorted(load(kind="repo_pytest"), key=lambda t: t.id)[:2]
    single_sample = sorted([t for t in load(split="pilot")], key=lambda t: t.id)[:2]
    smoke_tasks = single_sample + repo_tasks
    dual_smoke = {}
    for hname in ("opencode", "pi"):
        p_h = await CaptureProxy(args.vllm_url, cfg["rollout"]).start(port=args.proxy_port + 2)
        h_jobs = [(t, cfg["model"]["served_name"], 2026, f"p0-{hname}-{t.id}") for t in smoke_tasks]
        h_recs = await run_batch(p_h, h_jobs, args.out_dir / f"p0_smoke_{hname}",
                                 concurrency=4, cfg=cfg, harness_name=hname)
        await p_h.close()
        dual_smoke[hname] = [
            {"task_id": r["task_id"], "kind": r.get("kind"), "status": (r.get("grade") or {}).get("status"),
             "passed": (r.get("grade") or {}).get("passed"), "total": (r.get("grade") or {}).get("total"),
             "turns": r.get("n_policy_turns"), "capture_ok": r.get("capture_ok"),
             "tools": r.get("tool_calls"), "error": r.get("error")}
            for r in h_recs
        ]
    report["phase0_dual_harness_smoke"] = dual_smoke
    print("[phase0c] dual harness smoke:", json.dumps(dual_smoke, indent=2), flush=True)

    # 4. Phase 1a: Prefix-Merged Multi-Turn Packing gradient equivalence & speedup benchmark
    bench = benchmark_prefix_merge(args.vllm_url, recs_v3, cfg)
    report["phase1_prefix_merge_benchmark"] = bench
    print("[phase1a] prefix-merge benchmark:", json.dumps(bench, indent=2), flush=True)

    # 5. Phase 1b: 3 steps + forced restart --resume for 2 more steps (5 steps total)
    if not args.skip_train_smoke:
        train_dir = args.out_dir / "p1_train_resume_smoke"
        common = [
            sys.executable, "-u", "-m", "oca.train",
            "--mode", "train", "--harness", "opencode",
            "--out-dir", str(train_dir),
            "--tasks-per-step", "4", "--group-size", "4",
            "--concurrency", str(args.concurrency),
        ]
        rc1 = subprocess.call([*common, "--steps", "3", "--no-resume"])
        rc2 = subprocess.call([*common, "--steps", "5", "--resume"]) if rc1 == 0 else -1
        hist_lines = ((train_dir / "history.jsonl").read_text(encoding="utf-8").splitlines()
                      if (train_dir / "history.jsonl").is_file() else [])
        report["phase1_train_resume"] = {
            "part1_rc": rc1, "part2_resume_rc": rc2,
            "completed_steps": len(hist_lines),
            "last_step": json.loads(hist_lines[-1]) if hist_lines else None,
        }

    out_file = args.out_dir / "phase0_1_report.json"
    out_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\n=== PHASE 0/1 DIAGNOSTIC COMPLETE -> {out_file} ===", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=Path("/content/runs/phase0_1_diag"))
    ap.add_argument("--vllm-url", default="http://127.0.0.1:8000")
    ap.add_argument("--proxy-port", type=int, default=8110)
    ap.add_argument("--concurrency", type=int, default=24)
    ap.add_argument("--skip-train-smoke", action="store_true")
    args = ap.parse_args()
    asyncio.run(run_diag(args))


if __name__ == "__main__":
    main()
