"""One synchronous, on-policy LoRA GRPO update on an explicitly supplied G4."""

import json
import math
import os
from pathlib import Path
import tempfile
import time

from .contracts import (MODEL, PLAN, ROLLOUT, UPDATE, digest, first_update_groups,
                        require, targets, trace_segments, verify_snapshot, verify_three)


def one_step(three, groups_file, snapshot, destination):
    three_results = verify_three(three, verify_upstream=True)
    groups = first_update_groups(groups_file, verify_upstream=True)
    require(not set(item["trial_id"] for item in three_results.values()) & {group[0] for group in groups},
            "use fresh rollouts for first GRPO group")
    require(not destination.exists(), "output already exists")
    verify_snapshot(snapshot)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    import torch
    from torch.nn import functional as F
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM

    require(torch.cuda.device_count() == 1, "exactly one visible GPU is required")
    device = torch.cuda.get_device_properties(0)
    require("RTX PRO 6000 Blackwell" in device.name and
            device.total_memory >= PLAN["runtime"]["minimum_vram_bytes"], "expected Colab G4 96 GB")
    free, total = torch.cuda.mem_get_info()
    require(total - free < 2 * (1024 ** 3), "stop the rollout server and release the GPU before updating")
    torch.manual_seed(ROLLOUT["seed"])
    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    base = AutoModelForCausalLM.from_pretrained(
        str(snapshot), local_files_only=True, trust_remote_code=False,
        use_safetensors=True, torch_dtype=torch.bfloat16, device_map={"": 0},
    )
    base.requires_grad_(False)
    model = get_peft_model(base, LoraConfig(r=UPDATE["rank"], lora_alpha=UPDATE["alpha"],
        lora_dropout=UPDATE["dropout"], target_modules=UPDATE["targets"], bias="none", task_type="CAUSAL_LM"))
    model.config.use_cache = False
    model.train()
    trainable = {name: p for name, p in model.named_parameters() if p.requires_grad}
    require(trainable and all(".lora_" in name for name in trainable), "a non-LoRA parameter is trainable")
    frozen = [(p, p._version) for p in model.parameters() if not p.requires_grad]
    before = {name: p.detach().float().cpu().clone() for name, p in trainable.items()}
    opt = torch.optim.AdamW(trainable.values(), lr=UPDATE["lr"], weight_decay=0)
    opt.zero_grad(set_to_none=True)
    max_error, sum_error, n_error, losses = 0.0, 0.0, 0, 0.0

    for _, turns, advantage in groups:
        count = sum(len(targets(turn)) for turn in turns)
        for turn in turns:
            require(time.monotonic() - started < UPDATE["max_wall_seconds"], "update time budget exceeded")
            selected = targets(turn)
            if not selected:
                continue
            positions, labels, old = zip(*selected)
            ids = torch.tensor([turn["prompt_token_ids"] + turn["completion_token_ids"]], device="cuda")
            pos = torch.tensor(positions, device="cuda")
            expected = torch.tensor(labels, device="cuda")
            old = torch.tensor(old, dtype=torch.float32, device="cuda")
            logits = model(input_ids=ids, logits_to_keep=pos).logits[0].float()
            current = -F.cross_entropy(logits / ROLLOUT["temperature"], expected, reduction="none")
            error = (current.detach() - old).abs()
            this_max = float(error.max())
            require(math.isfinite(this_max) and this_max <= UPDATE["max_logprob_error_nats"],
                    "engine/trainer behavior logprob parity failed")
            max_error = max(max_error, this_max)
            sum_error += float(error.sum())
            n_error += len(selected)
            ratio = (current - old).exp()
            clip = UPDATE["clip_ratio"]
            loss = -torch.minimum(ratio * advantage, ratio.clamp(1 - clip, 1 + clip) * advantage).sum()
            loss = loss / (count * len(groups))
            loss.backward()
            losses += float(loss.detach())
            del logits, loss, current, ratio
            require(torch.cuda.max_memory_reserved() < PLAN["runtime"]["peak_stop_bytes"],
                    "allocator peak exceeded stop threshold")

    require(n_error and sum_error / n_error <= UPDATE["max_mean_logprob_error_nats"],
            "mean engine/trainer behavior logprob parity failed")
    grad = float(torch.nn.utils.clip_grad_norm_(trainable.values(), UPDATE["max_grad_norm"], error_if_nonfinite=True))
    require(math.isfinite(grad) and grad > 0, "zero or invalid LoRA gradient")
    opt.step()
    torch.cuda.synchronize()
    delta = math.sqrt(sum(float(((p.detach().float().cpu() - before[name]) ** 2).sum())
                          for name, p in trainable.items()))
    require(math.isfinite(delta) and delta > 0, "LoRA update is zero or invalid")
    require(all(p.grad is None and p._version == version for p, version in frozen),
            "a frozen base parameter changed")
    peak = torch.cuda.max_memory_reserved()
    require(peak < PLAN["runtime"]["peak_stop_bytes"], "allocator peak exceeded stop threshold")
    require(time.monotonic() - started < UPDATE["max_wall_seconds"], "update time budget exceeded")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".oca-step-", dir=destination.parent) as tmp:
        ready = Path(tmp) / "checkpoint"
        model.save_pretrained(ready, safe_serialization=True)
        adapter_sha = digest(ready / "adapter_model.safetensors")
        report = {
            "model_id": MODEL["id"], "model_revision": MODEL["revision"], "optimizer_steps": 1,
            "adapter_sha256": adapter_sha, "expected_served_alias": "oca-lora-" + adapter_sha[:16],
            "lora_delta_l2": delta, "gradient_norm_before_clipping": grad, "base_frozen": True,
            "mean_logprob_error_nats": sum_error / n_error, "max_logprob_error_nats": max_error,
            "loss": losses, "peak_reserved_vram_bytes": peak, "elapsed_seconds": time.monotonic() - started,
            "segments_by_trial": {trial: trace_segments(turns) for trial, turns, _ in groups},
        }
        (ready / "update.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        ready.rename(destination)
    return report
