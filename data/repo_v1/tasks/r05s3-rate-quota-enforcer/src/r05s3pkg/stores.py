from __future__ import annotations

import math
from r05s3pkg.policy import QuotaPolicy


class TokenBucketStore:
    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}

    def _project(self, policy: QuotaPolicy, now: float) -> tuple[float, float]:
        if policy.name not in self._buckets:
            return float(policy.burst), float(now)
        tokens, last_ts = self._buckets[policy.name]
        elapsed = max(0.0, float(now) - last_ts)
        updated_tokens = min(float(policy.burst), tokens + elapsed * policy.refill_rate)
        return updated_tokens, max(last_ts, float(now))

    def preview(self, policy: QuotaPolicy, cost: int, now: float) -> tuple[bool, int, float]:
        tokens, _ = self._project(policy, now)
        if tokens >= cost:
            return True, int(math.floor(tokens - cost)), 0.0
        deficit = cost - tokens
        retry_after = deficit / policy.refill_rate if policy.refill_rate > 0 else float("inf")
        return False, int(math.floor(tokens)), retry_after

    def consume(self, policy: QuotaPolicy, cost: int, now: float) -> tuple[bool, int, float]:
        tokens, effective_now = self._project(policy, now)
        if tokens >= cost:
            remaining = tokens - cost
            self._buckets[policy.name] = (remaining, effective_now)
            return True, int(math.floor(remaining)), 0.0
        self._buckets[policy.name] = (tokens, effective_now)
        deficit = cost - tokens
        retry_after = deficit / policy.refill_rate if policy.refill_rate > 0 else float("inf")
        return False, int(math.floor(tokens)), retry_after


class SlidingWindowStore:
    def __init__(self) -> None:
        self._windows: dict[str, list[tuple[float, int]]] = {}

    def _active_events(self, policy: QuotaPolicy, now: float) -> list[tuple[float, int]]:
        cutoff = float(now) - policy.window_seconds
        events = self._windows.get(policy.name, [])
        return [(ts, c) for ts, c in events if ts > cutoff]

    def preview(self, policy: QuotaPolicy, cost: int, now: float) -> tuple[bool, int, float]:
        active = self._active_events(policy, now)
        used = sum(c for _, c in active)
        if used + cost <= policy.limit:
            return True, policy.limit - (used + cost), 0.0

        needed_to_free = (used + cost) - policy.limit
        freed = 0
        retry_after = policy.window_seconds
        for ts, c in sorted(active, key=lambda item: item[0]):
            freed += c
            if freed >= needed_to_free:
                retry_after = max(0.0, (ts + policy.window_seconds) - float(now))
                break
        return False, max(0, policy.limit - used), retry_after

    def consume(self, policy: QuotaPolicy, cost: int, now: float) -> tuple[bool, int, float]:
        allowed, remaining, retry_after = self.preview(policy, cost, now)
        active = self._active_events(policy, now)
        if allowed:
            active.append((float(now), cost))
            self._windows[policy.name] = active
            return True, remaining, 0.0
        self._windows[policy.name] = active
        return False, remaining, retry_after
