from dataclasses import dataclass
from quotaguard.policy import RatePolicy
from quotaguard.store import TokenBucketStore


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    blocked_by: str | None
    remaining_min: float


class QuotaEnforcer:
    def __init__(self, store: TokenBucketStore | None = None) -> None:
        self.store = store if store is not None else TokenBucketStore()
        self._policies: dict[str, RatePolicy] = {}
        self._parents: dict[str, str | None] = {}

    def register_tenant(
        self,
        tenant_id: str,
        policy: RatePolicy,
        parent_id: str | None = None,
    ) -> None:
        if parent_id is not None and parent_id not in self._policies:
            raise KeyError(f"Parent tenant '{parent_id}' must be registered first")
        self._policies[tenant_id] = policy
        self._parents[tenant_id] = parent_id

    def get_lineage(self, tenant_id: str) -> list[str]:
        if tenant_id not in self._policies:
            raise KeyError(f"Unknown tenant '{tenant_id}'")
        chain: list[str] = []
        curr: str | None = tenant_id
        while curr is not None:
            chain.append(curr)
            curr = self._parents.get(curr)
        chain.reverse()
        return chain

    def check_and_consume(
        self,
        tenant_id: str,
        cost: float = 1.0,
        now: float = 0.0,
    ) -> QuotaDecision:
        if cost < 0:
            raise ValueError("Cost must be non-negative")

        lineage = self.get_lineage(tenant_id)
        remaining_values: list[float] = []

        for scope_id in lineage:
            policy = self._policies[scope_id]
            available = self.store.peek_tokens(policy, scope_id, now)
            if available < cost:
                return QuotaDecision(
                    allowed=False,
                    blocked_by=scope_id,
                    remaining_min=0.0,
                )
            new_balance = self.store.deduct(policy, scope_id, cost, now)
            remaining_values.append(new_balance)

        return QuotaDecision(
            allowed=True,
            blocked_by=None,
            remaining_min=min(remaining_values) if remaining_values else 0.0,
        )
