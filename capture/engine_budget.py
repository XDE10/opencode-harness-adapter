"""Account for requests on a single serial engine trial."""

import math


def validate_engine_logps(payload, expected_model):
    """Require a raw vLLM-format logprob for the exact engine token at each position."""
    try:
        choice = payload["choices"][0]
        prompt = payload["prompt_token_ids"]
        ids = choice["token_ids"]
        entries = choice["logprobs"]["content"]
        if (payload["model"] != expected_model or not isinstance(prompt, list) or not prompt
                or not isinstance(ids, list) or not ids or not isinstance(entries, list)
                or any(type(token) is not int or token < 0 for token in prompt + ids)
                or len(entries) != len(ids)):
            raise ValueError("missing model identity or incomplete token channels")
        for token, entry in zip(ids, entries):
            logp = entry["logprob"]
            if (entry["token"] != f"token_id:{token}" or type(logp) not in (int, float)
                    or not math.isfinite(logp) or logp > 0):
                raise ValueError("misaligned or invalid engine logprob")
    except (IndexError, KeyError, TypeError, ValueError):
        raise ValueError("engine identity, token IDs or logprobs failed validation") from None


class EngineBudget:
    token_limits = ("max_tokens", "max_completion_tokens", "max_output_tokens")

    def __init__(self, *, max_calls, per_call, per_trial):
        if any(type(limit) is not int or limit < 1 for limit in (max_calls, per_call, per_trial)):
            raise ValueError("invalid engine trial budget")
        self.max_calls = max_calls
        self.per_call = per_call
        self.per_trial = per_trial
        self.sent_limits = []
        self.output_tokens = 0
        self.pending = None
        self.failed = False

    def admit(self, body):
        if self.failed or self.pending is not None:
            raise ValueError("engine trial is stopped or already has a request in flight")
        remaining = self.per_trial - self.output_tokens
        if not remaining or len(self.sent_limits) >= self.max_calls:
            raise ValueError("engine trial budget exhausted")
        if (not isinstance(body, dict) or body.get("stream") is not False
                or type(body.get("n", 1)) is not int or body.get("n", 1) != 1):
            raise ValueError("expected one non-streaming engine completion")
        requested = [body[key] for key in self.token_limits if body.get(key) is not None]
        if any(type(value) is not int or value < 1 for value in requested):
            raise ValueError("invalid engine output limit")
        cap = min(self.per_call, remaining, *requested)
        bounded = {key: value for key, value in body.items() if key not in self.token_limits}
        bounded["max_tokens"] = cap
        self.pending = cap
        self.sent_limits.append(cap)
        return bounded

    def settle(self, payload):
        try:
            choices = payload["choices"]
            ids = choices[0]["token_ids"]
            count = payload["usage"]["completion_tokens"]
            if (len(choices) != 1 or not isinstance(ids, list) or type(count) is not int
                    or self.pending is None or not 0 < count == len(ids) <= self.pending):
                raise ValueError("bad count")
        except (IndexError, KeyError, TypeError, ValueError):
            self.failed = True
            raise ValueError("engine completion token accounting failed") from None
        self.output_tokens += count
        self.pending = None
