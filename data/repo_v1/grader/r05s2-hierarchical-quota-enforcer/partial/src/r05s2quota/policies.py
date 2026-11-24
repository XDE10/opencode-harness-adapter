from dataclasses import dataclass


@dataclass(frozen=True)
class QuotaPolicy:
    scope: str
    metric: str
    limit: int
    window_seconds: int
    priority: int = 0

    def __post_init__(self) -> None:
        if not self.scope or self.scope.startswith("/") or self.scope.endswith("/"):
            raise ValueError(f"Invalid scope: {self.scope!r}")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if self.limit < 0:
            raise ValueError("limit must be non-negative")


def iter_ancestor_scopes(scope: str) -> list[str]:
    parts = [p for p in scope.split("/") if p]
    return ["/".join(parts[: i + 1]) for i in range(len(parts))]


class PolicyRegistry:
    def __init__(self) -> None:
        self._policies: dict[tuple[str, str], QuotaPolicy] = {}

    def register(self, policy: QuotaPolicy) -> QuotaPolicy:
        key = (policy.scope, policy.metric)
        existing = self._policies.get(key)
        if existing is None:
            self._policies[key] = policy
            return policy

        if self._should_replace(existing, policy):
            self._policies[key] = policy
            return policy
        return existing

    @staticmethod
    def _should_replace(existing: QuotaPolicy, candidate: QuotaPolicy) -> bool:
        if candidate.priority != existing.priority:
            return candidate.priority > existing.priority
        existing_rate = existing.limit / existing.window_seconds
        candidate_rate = candidate.limit / candidate.window_seconds
        if candidate_rate != existing_rate:
            return candidate_rate < existing_rate
        return candidate.limit < existing.limit

    def get(self, scope: str, metric: str) -> QuotaPolicy | None:
        return self._policies.get((scope, metric))

    def resolve_chain(self, scope: str, metric: str) -> list[QuotaPolicy]:
        chain: list[QuotaPolicy] = []
        for ancestor in iter_ancestor_scopes(scope):
            policy = self._policies.get((ancestor, metric))
            if policy is not None:
                chain.append(policy)
        return chain
