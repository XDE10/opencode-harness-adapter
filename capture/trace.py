"""Shape checks for capture before it is exposed or sealed."""

import math

VOCAB_SIZE = 151936


def validate_turn(turn, *, vocabulary=VOCAB_SIZE, context=4096, output=512):
    fields = ("prompt_token_ids", "completion_token_ids", "per_token_logps", "loss_mask")
    if not isinstance(turn, dict) or not isinstance(turn.get("node_id"), str) or not turn["node_id"]:
        raise ValueError("missing capture node ID")
    for field in fields:
        if not isinstance(turn.get(field), list):
            raise ValueError(f"missing or invalid {field}")
    prompt, completion, logps, mask = (turn[field] for field in fields)
    if not prompt or not completion or len(prompt) + len(completion) > context or len(completion) > output:
        raise ValueError("invalid token counts or token budget exceeded")
    if any(type(tok) is not int or not 0 <= tok < vocabulary for tok in prompt + completion):
        raise ValueError("invalid token ID")
    if len(logps) != len(completion) or any(type(p) not in (int, float) or not math.isfinite(p) or p > 0 for p in logps):
        raise ValueError("misaligned or invalid per_token_logps")
    if len(mask) != len(prompt) + len(completion) or any(type(m) is not int or m not in (0, 1) for m in mask):
        raise ValueError("misaligned or invalid loss_mask")
    if any(mask[:len(prompt)]):
        raise ValueError("prompt and tool-result context must be masked")
