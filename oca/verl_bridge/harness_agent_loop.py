"""veRL `AgentLoopBase` adapter wrapping `oca.proxy.CaptureProxy` + unmodified OpenCode / Pi CLI harnesses.

Allows mounting real terminal coding agents directly inside `verl`'s asynchronous rollout worker
(`actor_rollout_ref.rollout.mode=async`, `agent_loop_config_path=oca/verl_bridge/harness_grpo.yaml`)
while preserving exact engine token IDs, processed behaviour logprobs, and loss masks (`response_mask`:
`1` on assistant generations, `0` on tool outputs / user turns).

Gracefully falls back to lightweight dataclass shims when `verl` is not installed locally so unit
tests verify the exact token-alignment contract on CPU.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import uuid

try:
    from verl.experimental.agent_loop.agent_loop import AgentLoopBase, AgentLoopOutput  # type: ignore
    VERL_AVAILABLE = True
except ImportError:
    VERL_AVAILABLE = False

    @dataclass
    class AgentLoopOutput:  # type: ignore[no-redef]
        prompt_ids: list[int]
        response_ids: list[int]
        response_mask: list[int]
        response_logprobs: list[float] | None = None
        num_turns: int = 0
        metrics: dict[str, Any] = field(default_factory=dict)
        extra_fields: dict[str, Any] = field(default_factory=dict)

    class AgentLoopBase:  # type: ignore[no-redef]
        def __init__(self, config: Any = None, server_manager: Any = None, tokenizer: Any = None, **kwargs):
            self.config = config
            self.server_manager = server_manager
            self.tokenizer = tokenizer


def trajectory_to_verl_output(
    turns: list[dict],
    reward: float | None = None,
    grade: dict | None = None,
    hack_flags: list[str] | None = None,
) -> AgentLoopOutput:
    """Convert multi-turn `CaptureProxy` policy turns into exact `verl.AgentLoopOutput` tensors.

    Contract:
    - `prompt_ids`: exact engine `prompt_token_ids` of the first valid policy turn.
    - `response_ids`: exact continuation tokens (assistant tokens + interleaved tool-observation tokens)
      for the maximal prefix-monotonic trajectory prefix.
    - `response_mask`: `1` strictly on assistant completion tokens, `0` strictly on tool/environment tokens.
    - `response_logprobs`: exact vLLM processed logprobs on mask=1 tokens, `0.0` on mask=0 tokens.
    - If context compaction breaks prefix monotonicity, stops at the longest contiguous segment and
      records `compaction_truncated=True` in `extra_fields` (caller can split segments if desired).
    """
    valid = [
        t for t in turns
        if not t.get("aux") and t.get("capture_ok")
        and t.get("prompt_token_ids") and t.get("completion_token_ids")
        and len(t["completion_token_ids"]) == len(t.get("per_token_logps") or [])
    ]
    if not valid:
        return AgentLoopOutput(
            prompt_ids=[], response_ids=[], response_mask=[], response_logprobs=[],
            num_turns=0, extra_fields={"capture_ok": False, "reward": reward},
        )

    first = valid[0]
    prompt_ids = list(first["prompt_token_ids"])
    full_seq = list(prompt_ids) + list(first["completion_token_ids"])
    response_ids = list(first["completion_token_ids"])
    response_mask = [1] * len(first["completion_token_ids"])
    response_logprobs = [float(x) for x in first["per_token_logps"]]
    used_turns = 1
    compaction_truncated = False

    for t in valid[1:]:
        p_ids = t["prompt_token_ids"]
        c_ids = t["completion_token_ids"]
        lps = t["per_token_logps"]
        if len(p_ids) < len(full_seq) or p_ids[:len(full_seq)] != full_seq:
            compaction_truncated = True
            break
        obs_delta = p_ids[len(full_seq):]
        response_ids.extend(obs_delta)
        response_mask.extend([0] * len(obs_delta))
        response_logprobs.extend([0.0] * len(obs_delta))

        response_ids.extend(c_ids)
        response_mask.extend([1] * len(c_ids))
        response_logprobs.extend(float(x) for x in lps)

        full_seq.extend(obs_delta)
        full_seq.extend(c_ids)
        used_turns += 1

    assert len(response_ids) == len(response_mask) == len(response_logprobs)
    return AgentLoopOutput(
        prompt_ids=prompt_ids,
        response_ids=response_ids,
        response_mask=response_mask,
        response_logprobs=response_logprobs,
        num_turns=used_turns,
        metrics={
            "n_policy_turns": used_turns,
            "n_assistant_tokens": sum(response_mask),
            "n_env_tokens": len(response_mask) - sum(response_mask),
        },
        extra_fields={
            "capture_ok": True,
            "compaction_truncated": compaction_truncated,
            "reward": reward,
            "grade": grade,
            "hack_flags": list(hack_flags or ()),
        },
    )


class HarnessAgentLoop(AgentLoopBase):
    """Drop-in `verl` AgentLoop executing unmodified OpenCode / Pi CLI harnesses through CaptureProxy."""

    async def run(self, sampling_params: dict[str, Any], **kwargs) -> AgentLoopOutput:
        from .. import CONFIG
        from ..proxy import CaptureProxy
        from ..rollout import run_trial
        from ..tasks import by_id

        task_id = kwargs["task_id"]
        harness_name = kwargs.get("harness", "opencode")
        vllm_url = kwargs.get("vllm_url", "http://127.0.0.1:8000")
        served_model = kwargs.get("served_model", CONFIG["model"]["served_name"])
        seed = int(kwargs.get("seed", 42))
        out_dir = Path(kwargs.get("out_dir", "/tmp/oca_verl_rollouts"))
        proxy = kwargs.get("proxy")

        cfg = dict(CONFIG)
        cfg["rollout"] = {**CONFIG["rollout"], **{k: v for k, v in sampling_params.items() if k in CONFIG["rollout"]}}
        task = kwargs.get("task") or by_id()[task_id]

        owns_proxy = proxy is None
        if owns_proxy:
            proxy = await CaptureProxy(
                vllm_url, cfg["rollout"], safe_intercept=bool(cfg["rollout"].get("safe_intercept", True))
            ).start(port=int(kwargs.get("proxy_port", 0)))
        try:
            trial_id = f"verl-{harness_name}-{task.id}-{uuid.uuid4().hex[:6]}"
            rec = await run_trial(
                proxy, task, served_model, seed, trial_id,
                out_dir=out_dir, cfg=cfg, harness_name=harness_name,
            )
        finally:
            if owns_proxy:
                await proxy.close()

        return trajectory_to_verl_output(
            rec.get("turns") or [],
            reward=rec.get("reward"),
            grade=rec.get("grade"),
            hack_flags=rec.get("hack_flags"),
        )
