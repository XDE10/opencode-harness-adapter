from typing import Any

from tiercache.directives import parse_cache_directive
from tiercache.store import TierStore


class TierCacheCoordinator:
    def __init__(self, l1_capacity: int = 4, l2_capacity: int = 8, default_ttl: int = 60) -> None:
        self.l1 = TierStore(l1_capacity)
        self.l2 = TierStore(l2_capacity)
        self.default_ttl = default_ttl
        self.backing_store: dict[str, Any] = {}

    def put_with_header(self, key: str, value: Any, header: str, now: int) -> bool:
        self.backing_store[key] = value
        policy = parse_cache_directive(header, default_ttl=self.default_ttl)

        if policy.no_store or policy.ttl == 0:
            self.l1.put(key, value, policy, now)
            self.l2.put(key, value, policy, now)
            return False

        self.l2.put(key, value, policy, now)
        if policy.tier == "L1":
            self.l1.put(key, value, policy, now)
        return True

    def fetch(self, key: str, now: int) -> tuple[Any | None, str]:
        val = self.l1.get(key, now)
        if val is not None:
            return val, "L1"
        val = self.l2.get(key, now)
        if val is not None:
            return val, "L2"
        if key in self.backing_store:
            return self.backing_store[key], "ORIGIN"
        return None, "MISS"

    def invalidate_tag(self, tag: str) -> list[str]:
        removed_l1 = set(self.l1.invalidate_tag(tag))
        removed_l2 = set(self.l2.invalidate_tag(tag))
        return sorted(removed_l1 | removed_l2)
