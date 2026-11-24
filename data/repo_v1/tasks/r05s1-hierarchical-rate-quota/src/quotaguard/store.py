from dataclasses import dataclass
from quotaguard.policy import RatePolicy


@dataclass
class BucketState:
    tokens: float
    last_timestamp: float


class TokenBucketStore:
    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], BucketState] = {}

    def _key(self, policy: RatePolicy, scope_id: str) -> tuple[str, str]:
        return (policy.name, scope_id)

    def sync_bucket(self, policy: RatePolicy, scope_id: str, now: float) -> BucketState:
        key = self._key(policy, scope_id)
        state = self._buckets.get(key)
        if state is None:
            state = BucketState(tokens=policy.burst_capacity, last_timestamp=now)
            self._buckets[key] = state
            return state

        elapsed = max(0.0, now - state.last_timestamp)
        if elapsed > 0.0:
            state.tokens = min(
                policy.burst_capacity,
                state.tokens + elapsed * policy.refill_rate_per_sec,
            )
            state.last_timestamp = now
        return state

    def peek_tokens(self, policy: RatePolicy, scope_id: str, now: float) -> float:
        state = self.sync_bucket(policy, scope_id, now)
        return state.tokens

    def deduct(self, policy: RatePolicy, scope_id: str, cost: float, now: float) -> float:
        state = self.sync_bucket(policy, scope_id, now)
        state.tokens -= cost
        return state.tokens
