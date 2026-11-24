from dataclasses import dataclass
from typing import Sequence

from r05s2quota.policies import PolicyRegistry
from r05s2quota.store import SlidingWindowStore


@dataclass(frozen=True)
class AcquireResult:
    allowed: bool
    violated_scope: str | None
    remaining: dict[str, int]


class QuotaEnforcer:
    def __init__(self, registry: PolicyRegistry, store: SlidingWindowStore | None = None) -> None:
        self.registry = registry
        self.store = store if store is not None else SlidingWindowStore()

    def acquire(self, scope: str, metric: str, amount: int, now: int) -> AcquireResult:
        if amount < 0:
            raise ValueError("amount must be non-negative")

        policies = self.registry.resolve_chain(scope, metric)
        if not policies:
            return AcquireResult(allowed=True, violated_scope=None, remaining={})

        remaining_after: dict[str, int] = {}
        for policy in policies:
            used = self.store.current_usage(policy.scope, metric, policy.window_seconds, now)
            if used + amount > policy.limit:
                current_rem = {
                    p.scope: max(0, p.limit - self.store.current_usage(p.scope, metric, p.window_seconds, now))
                    for p in policies
                }
                return AcquireResult(
                    allowed=False,
                    violated_scope=policy.scope,
                    remaining=current_rem,
                )
            self.store.record(policy.scope, metric, amount, now)
            remaining_after[policy.scope] = policy.limit - (used + amount)

        return AcquireResult(allowed=True, violated_scope=None, remaining=remaining_after)

    def acquire_batch(
        self,
        requests: Sequence[tuple[str, str, int]],
        now: int,
    ) -> list[AcquireResult]:
        results: list[AcquireResult] = []
        for scope, metric, amount in requests:
            res = self.acquire(scope, metric, amount, now)
            results.append(res)
            if not res.allowed:
                break
        return results

    def invalidate_subtree(self, root_scope: str, metric: str | None = None) -> int:
        root_scope = root_scope.strip("/")
        to_clear: list[tuple[str, str]] = []
        for scope, key_metric in self.store.keys():
            if scope.startswith(root_scope):
                if metric is None or key_metric == metric:
                    to_clear.append((scope, key_metric))
        return self.store.clear_keys(to_clear)
