"""Single-GPU colocated LoRA GRPO trainer & baseline difficulty screener.

Key engineering & RL components:
- Single-card colocation via vLLM Sleep Mode (`/sleep?level=1` <-> `/wake_up`) + runtime LoRA hot-swap
  (`/v1/load_lora_adapter` / `/v1/unload_lora_adapter`) with zero vLLM restarts.
- Prefix-Merged Multi-Turn Packing (`pack_trajectory_segments`): collapses monotonic multi-turn agent
  trajectories into single causal forward passes with exact `loss_mask` (zero on prompt + tool outputs)
  while automatically splitting whenever context compaction/rewriting breaks prefix continuity.
- Dual-ratio `TIS x DAPO Clip-Higher` (`tis_clip`) + `minibatches` + Policy Entropy monitoring, plus
  `ppo_clip`, `tis`, and `reinforce` modes for clean ablations.
- DAPO dynamic zero-variance group filtering with parallel 1.5x oversampling + curriculum ordering.
- Pluggable harnesses (`--harness opencode|pi`) and dual task kinds (`single_file` + `repo_pytest`).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import random
import shutil
import statistics
import subprocess
import time
import urllib.error
import urllib.request

from . import CONFIG, ROOT
from .proxy import CaptureProxy
from .rollout import run_batch
from .tasks import by_id, load

ERR_BINS = (0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 5.0)


def vllm_http(base_url: str, path: str, method: str = "GET", body: dict | None = None, timeout: int = 120):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if raw.strip().startswith(("{", "[")):
                return resp.status, json.loads(raw)
            return resp.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")[:800]


def ensure_vllm_running(vllm_url: str, cfg: dict, log_path: Path):
    try:
        st, _ = vllm_http(vllm_url, "/v1/models", timeout=3)
        if st == 200:
            vllm_http(vllm_url, "/wake_up", "POST", timeout=30)
            return
    except Exception:
        pass
    m = cfg["model"]
    t = cfg["train"]
    r = cfg["rollout"]
    env = os.environ.copy()
    env.update({
        "VLLM_SERVER_DEV_MODE": "1",
        "VLLM_ALLOW_RUNTIME_LORA_UPDATING": "True",
        "VLLM_NO_USAGE_STATS": "1",
    })
    cmd = [
        "vllm", "serve", m["local_path"],
        "--served-model-name", m["served_name"],
        "--host", "127.0.0.1", "--port", str(int(vllm_url.rsplit(":", 1)[-1])),
        "--dtype", "bfloat16", "--generation-config", "vllm",
        "--max-model-len", str(r["max_context_tokens"]),
        "--gpu-memory-utilization", str(t["vllm_gpu_memory_utilization"]),
        "--enable-sleep-mode",
        "--enable-auto-tool-choice", "--tool-call-parser", m.get("tool_call_parser", "qwen3_coder"),
        "--enable-lora", "--max-lora-rank", str(max(32, t["rank"])), "--max-loras", "2",
        "--logprobs-mode", "processed_logprobs", "--enable-prefix-caching",
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as lf:
        subprocess.Popen(cmd, env=env, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(150):
        time.sleep(4)
        try:
            st, _ = vllm_http(vllm_url, "/v1/models", timeout=3)
            if st == 200:
                return
        except Exception:
            pass
    raise RuntimeError(f"vLLM did not become ready on {vllm_url}; check {log_path}")


def vram_used_mib() -> int:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True, timeout=5
        )
        return int(out.strip().splitlines()[0])
    except Exception:
        return -1


def lock_grader_permissions():
    """When running as root on Colab, chmod 0700 all hidden grader dirs so `agent` cannot read them."""
    if os.name == "nt" or os.geteuid() != 0:
        return
    data_dir = ROOT / "data"
    candidates = [ROOT / "grader"]
    if data_dir.is_dir():
        for pat in ("tasks-*/grader", "repo_*/grader", "ood_*/grader"):
            candidates.extend(sorted(data_dir.glob(pat)))
    for gdir in candidates:
        if gdir.is_dir():
            os.chmod(gdir, 0o700)


def pack_trajectory_segments(turns: list[dict], adv: float, max_seq: int = 24576,
                             enable_merge: bool = True) -> tuple[list[dict], dict]:
    """Pack a single trajectory's policy turns into causal segments with exact next-token alignment.

    When `enable_merge=True`:
    - If turn k's `prompt_token_ids` strictly extends the previous segment's `input_ids`
      (`p_ids[:len(seg_ids)] == seg_ids`) and total length <= `max_seq`, we append the new
      tool-observation/user prompt tokens with `loss_mask=0`, followed by `completion_token_ids`
      with `loss_mask=1`. This avoids O(T^2) redundant prefix recomputation while remaining
      mathematically identical to per-turn forward passes in a causal Transformer.
    - If context compaction / history rewriting breaks the prefix invariant, we automatically close
      the current segment and start a new one, incrementing `rewrite_splits`.

    Returns `(segments, stats)` where each segment dict has:
      `input_ids`, `target_positions` (each == token_idx - 1), `target_ids`, `old_logps`, `adv`, `n_turns`.
    """
    valid_turns = []
    for turn in turns:
        if turn.get("aux") or not turn.get("capture_ok"):
            continue
        p_ids = turn.get("prompt_token_ids") or []
        c_ids = turn.get("completion_token_ids") or []
        lps = turn.get("per_token_logps") or []
        if not p_ids or not c_ids or len(c_ids) != len(lps):
            continue
        if len(p_ids) + len(c_ids) > max_seq:
            continue
        valid_turns.append((p_ids, c_ids, lps))

    segments: list[dict] = []
    rewrite_splits = 0
    length_splits = 0

    def _new_seg(p_ids, c_ids, lps):
        begin = len(p_ids)
        return {
            "input_ids": list(p_ids) + list(c_ids),
            "target_positions": [begin + i - 1 for i in range(len(c_ids))],
            "target_ids": list(c_ids),
            "old_logps": [float(x) for x in lps],
            "adv": float(adv),
            "n_turns": 1,
        }

    cur = None
    for p_ids, c_ids, lps in valid_turns:
        if not enable_merge or cur is None:
            if cur is not None:
                segments.append(cur)
            cur = _new_seg(p_ids, c_ids, lps)
            continue

        prev_ids = cur["input_ids"]
        is_prefix = len(p_ids) >= len(prev_ids) and p_ids[:len(prev_ids)] == prev_ids
        if not is_prefix:
            rewrite_splits += 1
            segments.append(cur)
            cur = _new_seg(p_ids, c_ids, lps)
        elif len(p_ids) + len(c_ids) > max_seq:
            length_splits += 1
            segments.append(cur)
            cur = _new_seg(p_ids, c_ids, lps)
        else:
            # Append new non-assistant tokens (tool outputs, mask=0), then new completion (mask=1)
            cur["input_ids"].extend(p_ids[len(prev_ids):])
            begin = len(cur["input_ids"])
            cur["input_ids"].extend(c_ids)
            cur["target_positions"].extend(begin + i - 1 for i in range(len(c_ids)))
            cur["target_ids"].extend(c_ids)
            cur["old_logps"].extend(float(x) for x in lps)
            cur["n_turns"] += 1

    if cur is not None:
        segments.append(cur)

    stats = {
        "raw_turns": len(valid_turns),
        "segments": len(segments),
        "rewrite_splits": rewrite_splits,
        "length_splits": length_splits,
        "total_tokens": sum(len(s["target_ids"]) for s in segments),
    }
    return segments, stats


def _split_backbone_lm_head(model):
    """Return (backbone, lm_head) for chunked logits on large-vocab models (e.g. Qwen3.5 248K)."""
    base = model.get_base_model() if hasattr(model, "get_base_model") else model
    lm_head = (base.get_output_embeddings() if hasattr(base, "get_output_embeddings")
               else getattr(base, "lm_head", None))
    backbone = getattr(base, "model", None) or getattr(base, "transformer", None)
    if backbone is not None and hasattr(backbone, "language_model"):
        backbone = backbone.language_model
    if backbone is None or lm_head is None:
        return None, None
    return backbone, lm_head


def _forward_target_logits(model, ids, pos_tensor, seq_len: int, min_pos: int):
    """Extract logits strictly at `pos_tensor` positions without materializing full [L, V] logits."""
    try:
        out = model(input_ids=ids, logits_to_keep=pos_tensor, use_cache=False).logits[0]
        if out.shape[0] == pos_tensor.shape[0]:
            return out.float()
    except Exception:
        pass
    # Fallback for Transformers versions where logits_to_keep only accepts an integer suffix length
    keep_n = seq_len - min_pos
    out = model(input_ids=ids, logits_to_keep=keep_n, use_cache=False).logits[0]
    rel = pos_tensor - min_pos
    return out.index_select(0, rel).float()


def _compute_target_logprobs_nograd(model, ids, pos_tensor, tgt_tensor, temp: float, chunk_size: int = 512):
    """Compute exact per-token logprobs under no_grad with chunked lm_head (~0.5 GB peak logits VRAM)."""
    import torch
    from torch.nn import functional as F
    backbone, lm_head = _split_backbone_lm_head(model)
    with torch.no_grad():
        if backbone is not None and lm_head is not None:
            h = backbone(input_ids=ids, use_cache=False).last_hidden_state[0].index_select(0, pos_tensor)
            out = []
            for s in range(0, h.shape[0], chunk_size):
                e = min(h.shape[0], s + chunk_size)
                lg = lm_head(h[s:e]).float() / temp
                out.append(-F.cross_entropy(lg, tgt_tensor[s:e], reduction="none"))
            return torch.cat(out, dim=0)
        logits = _forward_target_logits(model, ids, pos_tensor, int(ids.shape[1]), int(pos_tensor[0].item()))
        return -F.cross_entropy(logits / temp, tgt_tensor, reduction="none")


def _chunked_segment_loss_backward(
    model, seg: dict, temp: float, denom: float, loss_mode: str, tcfg: dict, chunk_size: int = 512,
) -> tuple[float, list[float], float, int, int]:
    """Exact GRPO/TIS-Clip loss & backward with chunked lm_head so 248K-vocab logits never OOM.

    Runs the transformer backbone forward once, computes exact per-chunk dL/dh over frozen lm_head
    in slices of `chunk_size` tokens (~0.5 GB peak VRAM), then runs backbone backward once with
    `h.backward(h_leaf.grad)`. Mathematically identical to full-tensor backward.
    """
    import torch
    from torch.nn import functional as F

    ids = torch.tensor([seg["input_ids"]], dtype=torch.long, device="cuda")
    pos = torch.tensor(seg["target_positions"], dtype=torch.long, device="cuda")
    tgt = torch.tensor(seg["target_ids"], dtype=torch.long, device="cuda")
    vllm_lp = torch.tensor(seg["old_logps"], dtype=torch.float32, device="cuda")
    hf_old_full = (torch.tensor(seg["hf_old_lp"], dtype=torch.float32, device="cuda")
                   if "hf_old_lp" in seg else None)
    adv = float(seg["adv"])
    n_tok = int(tgt.shape[0])

    def _slice_loss(scaled_logits, tgt_c, vllm_c, hf_old_c):
        log_probs = F.log_softmax(scaled_logits, dim=-1)
        cur_lp = log_probs.gather(-1, tgt_c.unsqueeze(-1)).squeeze(-1)
        with torch.no_grad():
            ent_sum = float((-(log_probs.exp() * log_probs).sum(dim=-1)).sum().item())
        hf_old = hf_old_c if hf_old_c is not None else cur_lp.detach()
        abs_err = (hf_old - vllm_c).abs()
        tis_c = 0
        ppo_c = 0
        if loss_mode == "tis_clip":
            log_r_eng = (hf_old - vllm_c).clamp(-10.0, 10.0)
            raw_eng = log_r_eng.exp()
            tis_cap = float(tcfg["tis_cap"])
            tis_c = int((raw_eng > tis_cap).sum().item())
            tis_w = raw_eng.clamp(max=tis_cap) * (abs_err <= 5.0).float()

            ratio = (cur_lp - hf_old).clamp(-10.0, 10.0).exp()
            clamped = ratio.clamp(1.0 - tcfg["clip_low"], 1.0 + tcfg["clip_high"])
            ppo_c = int((ratio.detach() != clamped.detach()).sum().item())
            loss_c = -(tis_w * torch.minimum(ratio * adv, clamped * adv)).sum() / denom
        elif loss_mode == "tis":
            log_r = (cur_lp.detach() - vllm_c).clamp(-10.0, 10.0)
            raw_r = log_r.exp()
            tis_cap = float(tcfg["tis_cap"])
            tis_c = int((raw_r > tis_cap).sum().item())
            tis_w = raw_r.clamp(max=tis_cap) * (abs_err <= 5.0).float()
            loss_c = -(tis_w * adv * cur_lp).sum() / denom
        elif loss_mode == "ppo_clip":
            ratio = (cur_lp - vllm_c).clamp(-10.0, 10.0).exp()
            clamped = ratio.clamp(1.0 - tcfg["clip_low"], 1.0 + tcfg["clip_high"])
            ppo_c = int((ratio.detach() != clamped.detach()).sum().item())
            loss_c = -torch.minimum(ratio * adv, clamped * adv).sum() / denom
        else:
            loss_c = -(adv * cur_lp).sum() / denom
        return loss_c, abs_err.detach().cpu().tolist(), ent_sum, tis_c, ppo_c

    backbone, lm_head = _split_backbone_lm_head(model)
    loss_acc = 0.0
    errs_out: list[float] = []
    ent_total = 0.0
    tis_total = 0
    ppo_total = 0

    if backbone is not None and lm_head is not None:
        h = backbone(input_ids=ids, use_cache=False).last_hidden_state[0].index_select(0, pos)
        h_leaf = h.detach().requires_grad_(True)
        for s in range(0, n_tok, chunk_size):
            e = min(n_tok, s + chunk_size)
            scaled = lm_head(h_leaf[s:e]).float() / temp
            hf_c = hf_old_full[s:e] if hf_old_full is not None else None
            loss_c, err_c, ent_c, tc, pc = _slice_loss(scaled, tgt[s:e], vllm_lp[s:e], hf_c)
            if loss_c.requires_grad:
                loss_c.backward()
            loss_acc += float(loss_c.detach().item())
            errs_out.extend(err_c)
            ent_total += ent_c
            tis_total += tc
            ppo_total += pc
            del scaled, loss_c
        if h_leaf.grad is not None:
            h.backward(h_leaf.grad)
        del h, h_leaf
    else:
        logits = _forward_target_logits(model, ids, pos, len(seg["input_ids"]), seg["target_positions"][0])
        loss_c, err_c, ent_c, tc, pc = _slice_loss(logits / temp, tgt, vllm_lp, hf_old_full)
        if loss_c.requires_grad:
            loss_c.backward()
        loss_acc = float(loss_c.detach().item())
        errs_out = err_c
        ent_total = ent_c
        tis_total = tc
        ppo_total = pc
        del logits, loss_c

    del ids, pos, tgt, vllm_lp, hf_old_full
    return loss_acc, errs_out, (ent_total / max(1, n_tok)), tis_total, ppo_total


async def run_screen(args, cfg: dict):
    lock_grader_permissions()
    ensure_vllm_running(args.vllm_url, cfg, args.out_dir / "vllm.log")
    tasks = sorted(load(split="train", kind=args.kind or None), key=lambda t: t.id)
    if args.shard:
        idx, total = map(int, args.shard.split("/"))
        tasks = [t for i, t in enumerate(tasks) if i % total == idx]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    trials_dir = args.out_dir / "trials"
    trials_dir.mkdir(exist_ok=True)

    jobs = []
    existing = {}
    for t in tasks:
        for k in range(args.k):
            tid = f"scr-{args.harness}-{t.id}-s{k}"
            rec_file = trials_dir / f"{tid}.json"
            if rec_file.is_file():
                existing[tid] = json.loads(rec_file.read_text(encoding="utf-8"))
            else:
                jobs.append((t, cfg["model"]["served_name"], 10_000 + k, tid))

    print(f"[screen:{args.harness}] {len(tasks)} tasks x {args.k} = {len(tasks)*args.k} trials "
          f"({len(existing)} cached, {len(jobs)} to run)", flush=True)
    if jobs:
        proxy = await CaptureProxy(args.vllm_url, cfg["rollout"]).start(port=args.proxy_port)
        done = 0

        def on_done(rec):
            nonlocal done
            done += 1
            if done % 8 == 0 or done == len(jobs):
                st = (rec.get("grade") or {}).get("status", "err")
                print(f"  [screen {done}/{len(jobs)}] last={rec['task_id']} status={st} "
                      f"turns={rec.get('n_policy_turns')} wall={rec.get('wall_s')}s", flush=True)

        fresh = await run_batch(
            proxy, jobs, trials_dir, concurrency=args.concurrency, cfg=cfg,
            on_done=on_done, harness_name=args.harness,
        )
        await proxy.close()
        for r in fresh:
            existing[r["trial_id"]] = r

    per_task = []
    for t in tasks:
        recs = [existing[f"scr-{args.harness}-{t.id}-s{k}"] for k in range(args.k)]
        passes = sum(1 for r in recs if (r.get("grade") or {}).get("status") == "pass" and not r.get("hack_flags"))
        avg_toks = statistics.mean(r.get("completion_tokens", 0) for r in recs)
        avg_turns = statistics.mean(r.get("n_policy_turns", 0) for r in recs)
        per_task.append({
            "task_id": t.id, "kind": t.kind, "domain": t.domain, "source": t.source,
            "passed": passes, "k": args.k, "pass_rate": passes / args.k,
            "avg_completion_tokens": round(avg_toks, 1), "avg_turns": round(avg_turns, 2),
        })

    informative = [row["task_id"] for row in per_task if 0 < row["passed"] < args.k]
    hard_solvable = [row["task_id"] for row in per_task if row["passed"] == 0]
    trivial = [row["task_id"] for row in per_task if row["passed"] == args.k]
    summary = {
        "harness": args.harness, "n_tasks": len(per_task), "k": args.k, "shard": args.shard,
        "n_informative_1_to_k_minus_1": len(informative),
        "n_zero_pass": len(hard_solvable),
        "n_all_pass": len(trivial),
        "mean_pass_at_1": round(statistics.mean(r["pass_rate"] for r in per_task), 4) if per_task else 0.0,
        "informative_task_ids": informative,
        "per_task": per_task,
    }
    (args.out_dir / "screen_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("[screen] summary:", json.dumps({k: v for k, v in summary.items() if k != "per_task"}, indent=2), flush=True)


def hot_load_lora(vllm_url: str, new_alias: str, ckpt_dir: Path, prev_alias: str | None) -> dict:
    t0 = time.time()
    st_load, r_load = vllm_http(vllm_url, "/v1/load_lora_adapter", "POST", {
        "lora_name": new_alias, "lora_path": str(ckpt_dir.resolve()),
    })
    if st_load != 200:
        raise RuntimeError(f"load_lora_adapter failed ({st_load}): {r_load}")
    if prev_alias and prev_alias != new_alias:
        vllm_http(vllm_url, "/v1/unload_lora_adapter", "POST", {"lora_name": prev_alias})
    st_m, models_resp = vllm_http(vllm_url, "/v1/models")
    model_ids = [m["id"] for m in (models_resp.get("data") or [])] if isinstance(models_resp, dict) else []
    if new_alias not in model_ids:
        raise RuntimeError(f"new LoRA {new_alias} missing from /v1/models: {model_ids}")
    st_c, canary = vllm_http(vllm_url, "/v1/chat/completions", "POST", {
        "model": new_alias, "messages": [{"role": "user", "content": "OK"}],
        "max_tokens": 2, "temperature": 0.0, "chat_template_kwargs": {"enable_thinking": False},
    })
    if st_c != 200:
        raise RuntimeError(f"canary failed on {new_alias}: {canary}")
    return {"alias": new_alias, "swap_seconds": round(time.time() - t0, 3),
            "canary_model": canary.get("model"), "advertised_models": model_ids}


def run_train(args, cfg: dict):
    import torch
    from torch.nn import functional as F
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM

    lock_grader_permissions()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ensure_vllm_running(args.vllm_url, cfg, args.out_dir / "vllm.log")

    tcfg = dict(cfg["train"])
    if args.loss_mode:
        tcfg["loss_mode"] = args.loss_mode
    if args.norm_mode:
        tcfg["norm_mode"] = args.norm_mode
    if args.minibatches:
        tcfg["minibatches"] = args.minibatches
    if args.prefix_merge is not None:
        tcfg["prefix_merge"] = args.prefix_merge
    if args.efficiency_weight is not None:
        tcfg["efficiency_weight"] = args.efficiency_weight
        cfg["train"]["efficiency_weight"] = args.efficiency_weight
    if args.reward_mode:
        tcfg["reward_mode"] = args.reward_mode
        cfg["train"]["reward_mode"] = args.reward_mode
    if args.steps:
        tcfg["steps"] = args.steps
    if args.tasks_per_step:
        tcfg["tasks_per_step"] = args.tasks_per_step
    if args.group_size:
        tcfg["group_size"] = args.group_size
    if args.rank:
        tcfg["rank"] = args.rank
        tcfg["alpha"] = args.rank * 2

    loss_mode = tcfg.get("loss_mode", "tis_clip")
    norm_mode = tcfg.get("norm_mode", "token")
    prefix_merge = bool(tcfg.get("prefix_merge", True))
    minibatches = max(1, int(tcfg.get("minibatches", 2)))
    oversample = float(tcfg.get("oversample_factor", 1.5))
    steps = tcfg["steps"]
    G = tcfg["group_size"]
    B = tcfg["tasks_per_step"]
    temp = cfg["rollout"]["temperature"]
    max_seq = tcfg.get("max_train_tokens", 28672)

    all_tasks = by_id()
    if args.task_ids_file and args.task_ids_file.is_file():
        doc = json.loads(args.task_ids_file.read_text(encoding="utf-8"))
        ids = doc["informative_task_ids"] if isinstance(doc, dict) and "informative_task_ids" in doc else doc
        pool = [all_tasks[i] for i in ids if i in all_tasks and all_tasks[i].split == "train"]
        if isinstance(doc, dict) and "per_task" in doc and args.curriculum:
            rates = {r["task_id"]: r["pass_rate"] for r in doc["per_task"]}
            pool.sort(key=lambda x: (-rates.get(x.id, 0.5), x.id))
    else:
        pool = load(split="train", kind=args.kind or None)
    if not pool:
        raise SystemExit("Empty training task pool")
    print(f"[train:{args.harness}] pool={len(pool)} | steps={steps} | B={B}xG={G} | r={tcfg['rank']} | "
          f"loss={loss_mode} | mb={minibatches} | prefix_merge={prefix_merge} | norm={norm_mode} | "
          f"eff_w={cfg['train']['efficiency_weight']}", flush=True)

    vllm_http(args.vllm_url, "/sleep?level=1", "POST")
    total_vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    offload_trainer = total_vram_gb < 75.0

    ckpt_root = args.out_dir / "checkpoints"
    ckpt_root.mkdir(exist_ok=True)
    existing_ckpts = sorted(ckpt_root.glob("step_*"))
    start_step = 1
    active_alias = None

    base = AutoModelForCausalLM.from_pretrained(
        cfg["model"]["local_path"], local_files_only=True, dtype=torch.bfloat16,
        attn_implementation="sdpa", device_map={"": 0},
    )
    base.requires_grad_(False)
    base.config.use_cache = False
    base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    base.enable_input_require_grads()

    if args.resume and existing_ckpts:
        last_ckpt = existing_ckpts[-1]
        start_step = int(last_ckpt.name.split("_")[-1]) + 1
        model = PeftModel.from_pretrained(base, str(last_ckpt), is_trainable=True)
        active_alias = f"lora-step-{start_step - 1}"
        print(f"[train] resumed LoRA from {last_ckpt} -> next step {start_step}", flush=True)
    else:
        lora_cfg = LoraConfig(
            r=tcfg["rank"], lora_alpha=tcfg["alpha"], lora_dropout=0.0,
            target_modules=tcfg["targets"], bias="none", task_type="CAUSAL_LM",
        )
        model = get_peft_model(base, lora_cfg)

    model.train()
    trainable = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(trainable, lr=tcfg["lr"], weight_decay=0.0)
    opt_state_file = ckpt_root / "latest_optim.pt"
    if args.resume and existing_ckpts and opt_state_file.is_file():
        opt.load_state_dict(torch.load(opt_state_file, map_location="cuda"))

    if offload_trainer:
        model.to("cpu")
        torch.cuda.empty_cache()

    vllm_http(args.vllm_url, "/wake_up", "POST")
    if active_alias:
        hot_load_lora(args.vllm_url, active_alias, existing_ckpts[-1], None)

    rng = random.Random(args.seed)
    history_path = args.out_dir / "history.jsonl"

    async def collect_step_groups(step_idx: int, served_model: str):
        step_dir = args.out_dir / "rollouts" / f"step_{step_idx:03d}"
        step_dir.mkdir(parents=True, exist_ok=True)
        proxy = await CaptureProxy(args.vllm_url, cfg["rollout"]).start(port=args.proxy_port)
        admitted_groups = []
        all_records = []
        zero_var = 0
        cursor_pool = list(pool)
        if not args.curriculum:
            rng.shuffle(cursor_pool)
        else:
            win = max(B * 3, int(len(pool) * min(1.0, 0.4 + 0.6 * step_idx / max(1, steps))))
            sub = cursor_pool[:win]
            rng.shuffle(sub)
            cursor_pool = sub + cursor_pool[win:]

        used_tasks = set()
        max_rounds = 2 if args.dynamic_sampling else 1
        for rnd in range(max_rounds):
            need_groups = B - len(admitted_groups)
            if need_groups <= 0:
                break
            # Oversample in round 0 to eliminate serial waiting on zero-variance drops
            n_pick = math.ceil(need_groups * oversample) if (rnd == 0 and args.dynamic_sampling) else need_groups
            chosen = [t for t in cursor_pool if t.id not in used_tasks][:n_pick]
            if not chosen:
                break
            for t in chosen:
                used_tasks.add(t.id)
            jobs = [
                (t, served_model, args.seed * 100_000 + step_idx * 1_000 + rnd * 100 + g,
                 f"s{step_idx:03d}-r{rnd}-{t.id}-g{g}")
                for t in chosen for g in range(G)
            ]
            recs = await run_batch(
                proxy, jobs, step_dir, concurrency=args.concurrency, cfg=cfg, harness_name=args.harness
            )
            all_records.extend(recs)
            by_task: dict[str, list[dict]] = {}
            for rec in recs:
                by_task.setdefault(rec["task_id"], []).append(rec)
            for tid, trecs in by_task.items():
                valid_recs = [r for r in trecs if r.get("reward") is not None and r.get("capture_ok")]
                if len(valid_recs) < 2:
                    continue
                rews = [r["reward"] for r in valid_recs]
                sd = statistics.pstdev(rews)
                if sd < 1e-6 and args.dynamic_sampling:
                    zero_var += 1
                    continue
                mean_r = statistics.mean(rews)
                advs = [(r, (r["reward"] - mean_r) / (sd + 1e-4) if sd >= 1e-6 else 0.0) for r in valid_recs]
                if any(abs(a) > 1e-6 for _, a in advs):
                    admitted_groups.append((tid, advs))
                else:
                    zero_var += 1
            if len(admitted_groups) >= B:
                admitted_groups = admitted_groups[:B]
                break
        await proxy.close()
        return admitted_groups, all_records, zero_var

    for step in range(start_step, steps + 1):
        step_t0 = time.time()
        served_model = active_alias or cfg["model"]["served_name"]

        t_roll0 = time.time()
        admitted_groups, all_recs, zero_var = asyncio.run(collect_step_groups(step, served_model))
        rollout_s = time.time() - t_roll0
        vram_rollout_mib = vram_used_mib()

        valid_all = [r for r in all_recs if r.get("reward") is not None]
        pass_rate = (sum(1 for r in valid_all if (r.get("grade") or {}).get("status") == "pass" and not r.get("hack_flags")) / len(valid_all)
                     if valid_all else 0.0)
        mean_reward = statistics.mean(r["reward"] for r in valid_all) if valid_all else 0.0
        mean_toks = statistics.mean(r.get("completion_tokens", 0) for r in valid_all) if valid_all else 0.0
        mean_turns = statistics.mean(r.get("n_policy_turns", 0) for r in valid_all) if valid_all else 0.0
        n_hacks = sum(1 for r in valid_all if r.get("hack_flags"))

        t_slp0 = time.time()
        vllm_http(args.vllm_url, "/sleep?level=1", "POST")
        sleep_s = time.time() - t_slp0
        vram_slept_mib = vram_used_mib()

        t_trn0 = time.time()
        if offload_trainer:
            model.to("cuda")
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

        # Pack trajectories into prefix-merged causal segments
        segments = []
        raw_turns_total = 0
        rewrite_splits_total = 0
        n_trajs = 0
        for _, adv_pairs in admitted_groups:
            for rec, adv in adv_pairs:
                if abs(adv) < 1e-8:
                    continue
                segs, st = pack_trajectory_segments(rec["turns"], float(adv), max_seq=max_seq, enable_merge=prefix_merge)
                if not segs:
                    continue
                n_trajs += 1
                raw_turns_total += st["raw_turns"]
                rewrite_splits_total += st["rewrite_splits"]
                traj_toks = max(1, st["total_tokens"])
                for s in segs:
                    s["traj_tokens"] = traj_toks
                    segments.append(s)

        total_tokens = sum(len(s["target_ids"]) for s in segments)
        errs = []
        entropies = []
        tis_clipped = 0
        ppo_clipped = 0
        total_loss_val = 0.0
        grad_norms = []
        mb_executed = 0

        if segments and total_tokens > 0:
            effective_mb = min(minibatches, len(segments))
            rng.shuffle(segments)
            chunks = [segments[i::effective_mb] for i in range(effective_mb)]
            # Pre-cache pi_HF,old only for chunks[1:] (chunk 0 runs before any opt.step(), so cur_lp == hf_old)
            if effective_mb > 1:
                for chunk in chunks[1:]:
                    for seg in chunk:
                        ids = torch.tensor([seg["input_ids"]], dtype=torch.long, device="cuda")
                        pos = torch.tensor(seg["target_positions"], dtype=torch.long, device="cuda")
                        tgt = torch.tensor(seg["target_ids"], dtype=torch.long, device="cuda")
                        lp = _compute_target_logprobs_nograd(model, ids, pos, tgt, temp, chunk_size=512)
                        seg["hf_old_lp"] = lp.cpu().tolist()
                        del ids, pos, tgt, lp

            for chunk in chunks:
                if not chunk:
                    continue
                opt.zero_grad(set_to_none=True)
                mb_tokens = sum(len(s["target_ids"]) for s in chunk)
                mb_trajs = max(1, len(chunk))
                mb_loss_acc = 0.0

                for seg in chunk:
                    denom = float((seg["traj_tokens"] * mb_trajs) if norm_mode == "trajectory" else mb_tokens)
                    l_val, seg_errs, seg_ent, seg_tis, seg_ppo = _chunked_segment_loss_backward(
                        model, seg, temp, denom, loss_mode, tcfg, chunk_size=512,
                    )
                    mb_loss_acc += l_val
                    errs.extend(seg_errs)
                    entropies.append(seg_ent)
                    tis_clipped += seg_tis
                    ppo_clipped += seg_ppo

                gn = float(torch.nn.utils.clip_grad_norm_(trainable, tcfg["max_grad_norm"]).item())
                if math.isfinite(gn) and gn > 0:
                    opt.step()
                    mb_executed += 1
                    grad_norms.append(gn)
                total_loss_val += mb_loss_acc
                opt.zero_grad(set_to_none=True)

        grad_norm = statistics.mean(grad_norms) if grad_norms else 0.0
        torch.cuda.synchronize()
        peak_train_mib = int(torch.cuda.max_memory_reserved() // (1024 * 1024))

        ckpt_dir = ckpt_root / f"step_{step:03d}"
        model.save_pretrained(ckpt_dir, safe_serialization=True)
        torch.save(opt.state_dict(), opt_state_file)
        if args.backup_dir:
            bdir = Path(args.backup_dir) / f"step_{step:03d}"
            bdir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(ckpt_dir, bdir, dirs_exist_ok=True)

        if offload_trainer:
            model.to("cpu")
        torch.cuda.empty_cache()
        train_s = time.time() - t_trn0

        t_wake0 = time.time()
        vllm_http(args.vllm_url, "/wake_up", "POST")
        new_alias = f"lora-step-{step}"
        swap_info = hot_load_lora(args.vllm_url, new_alias, ckpt_dir, active_alias)
        active_alias = new_alias
        wake_swap_s = time.time() - t_wake0

        errs_sorted = sorted(errs)
        n_e = len(errs_sorted)
        hist = {}
        prev_b = 0.0
        for b in ERR_BINS:
            hist[f"{prev_b}-{b}"] = sum(1 for x in errs_sorted if prev_b <= x < b)
            prev_b = b
        hist[f">={ERR_BINS[-1]}"] = sum(1 for x in errs_sorted if x >= ERR_BINS[-1])

        row = {
            "step": step,
            "harness": args.harness,
            "loss_mode": loss_mode,
            "norm_mode": norm_mode,
            "prefix_merge": prefix_merge,
            "served_model": served_model,
            "loaded_alias": active_alias,
            "n_trials": len(valid_all),
            "admitted_groups": len(admitted_groups),
            "zero_var_groups_dropped": zero_var,
            "pass_rate": round(pass_rate, 4),
            "mean_reward": round(mean_reward, 4),
            "mean_completion_tokens": round(mean_toks, 1),
            "mean_turns": round(mean_turns, 2),
            "hack_flagged_trials": n_hacks,
            "raw_policy_turns": raw_turns_total,
            "packed_segments": len(segments),
            "prefix_rewrite_splits": rewrite_splits_total,
            "prefix_compression_ratio": round(raw_turns_total / len(segments), 2) if segments else 1.0,
            "trained_tokens": total_tokens,
            "minibatches_executed": mb_executed,
            "loss": round(total_loss_val / max(1, mb_executed), 6),
            "grad_norm": round(grad_norm, 4),
            "policy_entropy": round(statistics.mean(entropies), 4) if entropies else 0.0,
            "logprob_err_mean": round(statistics.mean(errs_sorted), 5) if n_e else 0.0,
            "logprob_err_p99": round(errs_sorted[min(n_e - 1, int(0.99 * n_e))], 5) if n_e else 0.0,
            "logprob_err_max": round(errs_sorted[-1], 5) if n_e else 0.0,
            "n_tokens_over_05_nats": sum(1 for x in errs_sorted if x > 0.5),
            "tis_clipped_tokens": tis_clipped,
            "ppo_clipped_tokens": ppo_clipped,
            "logprob_err_hist": hist,
            "timing_s": {
                "rollout": round(rollout_s, 2),
                "sleep": round(sleep_s, 2),
                "train": round(train_s, 2),
                "wake_and_hotswap": round(wake_swap_s, 2),
                "lora_swap_only": swap_info["swap_seconds"],
                "total": round(time.time() - step_t0, 2),
            },
            "vram_mib": {
                "rollout": vram_rollout_mib,
                "slept": vram_slept_mib,
                "train_peak_reserved": peak_train_mib,
            },
        }
        (ckpt_dir / "step_metrics.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        with history_path.open("a", encoding="utf-8") as hf:
            hf.write(json.dumps(row) + "\n")
        print(f"[step {step:02d}/{steps}] pass={pass_rate*100:5.1f}% rew={mean_reward:.3f} "
              f"groups={len(admitted_groups)}(drop={zero_var}) segs={len(segments)}/{raw_turns_total} "
              f"ent={row['policy_entropy']:.3f} grad={grad_norm:.3f} err_max={row['logprob_err_max']:.3f} "
              f"time={row['timing_s']['total']:.0f}s(trn={train_s:.1f}s,swap={swap_info['swap_seconds']:.2f}s)",
              flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("screen", "train"), required=True)
    ap.add_argument("--harness", choices=("opencode", "pi"), default="opencode")
    ap.add_argument("--kind", choices=("", "single_file", "repo_pytest"), default="")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--vllm-url", default="http://127.0.0.1:8000")
    ap.add_argument("--proxy-port", type=int, default=8100)
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--seed", type=int, default=42)
    # Screen args
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--shard", type=str, default="")
    # Train args
    ap.add_argument("--task-ids-file", type=Path, default=None)
    ap.add_argument("--steps", type=int, default=0)
    ap.add_argument("--tasks-per-step", type=int, default=0)
    ap.add_argument("--group-size", type=int, default=0)
    ap.add_argument("--rank", type=int, default=0)
    ap.add_argument("--minibatches", type=int, default=0)
    ap.add_argument("--loss-mode", choices=("", "tis_clip", "tis", "ppo_clip", "reinforce"), default="")
    ap.add_argument("--norm-mode", choices=("", "token", "trajectory"), default="")
    ap.add_argument("--prefix-merge", action=argparse.BooleanOptionalAction, default=None)
    ap.add_argument("--reward-mode", choices=("", "binary", "partial"), default="")
    ap.add_argument("--efficiency-weight", type=float, default=None)
    ap.add_argument("--dynamic-sampling", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--curriculum", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--backup-dir", type=Path, default=None)
    args = ap.parse_args()

    cfg = json.loads(json.dumps(CONFIG))
    if args.mode == "screen":
        asyncio.run(run_screen(args, cfg))
    else:
        run_train(args, cfg)


if __name__ == "__main__":
    main()
