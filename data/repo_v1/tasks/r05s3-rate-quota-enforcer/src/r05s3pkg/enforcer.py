from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from r05s3pkg.policy import QuotaPolicy, parse_policy_spec
from r05s3pkg.stores import SlidingWindowStore, TokenBucketStore


@dataclass(frozen=True)
class EnforcementResult:
    allowed: bool
    denied_by: str | None
    retry_after: float
    remaining_by_policy: dict[str, int]


class HierarchicalEnforcer:
    def __init__(self) -> None:
        self._policies_by_scope: dict[str, list[QuotaPolicy]] = {}
        self._token_store = TokenBucketStore()
        self._window_store = SlidingWindowStore()

    def register_policy(self, policy_or_spec: QuotaPolicy | dict[str, Any]) -> QuotaPolicy:
        policy = (
            policy_or_spec
            if isinstance(policy_or_spec, QuotaPolicy)
            else parse_policy_spec(policy_or_spec)
        )
        bucket = self._policies_by_scope.setdefault(policy.scope, [])
        bucket.append(policy)
        return policy

    def _store_for(self, policy: QuotaPolicy) -> TokenBucketStore | SlidingWindowStore:
        if policy.algorithm == "token_bucket":
            return self._token_store
        return self._window_store

    def get_remaining(self, scopes: Iterable[str], now: float) -> dict[str, int]:
        snapshot: dict[str, int] = {}
        for scope in scopes:
            for policy in self._policies_by_scope.get(scope, ()):
                store = self._store_for(policy)
                _, remaining, _ = store.preview(policy, cost=0, now=now)
                snapshot[policy.name] = remaining
        return snapshot

    def check_and_consume(
        self,
        scopes: Iterable[str],
        cost: int = 1,
        now: float = 0.0,
    ) -> EnforcementResult:
        if cost <= 0:
            raise ValueError("cost must be a positive integer")

        scope_list = list(scopes)
        matching_policies: list[QuotaPolicy] = []
        for scope in scope_list:
            matching_policies.extend(self._policies_by_scope.get(scope, ()))

        remaining_map: dict[str, int] = {}
        for policy in matching_policies:
            store = self._store_for(policy)
            allowed, remaining, retry_after = store.consume(policy, cost=cost, now=now)
            remaining_map[policy.name] = remaining
            if not allowed:
                return EnforcementResult(
                    allowed=False,
                    denied_by=policy.name,
                    retry_after=retry_after,
                    remaining_by_policy=remaining_map,
                )

        return EnforcementResult(
            allowed=True,
            denied_by=None,
            retry_after=0.0,
            remaining_by_policy=remaining_map,
        )
