from typing import Any, Callable, Iterable, Sequence
from r12s2cache.registry import CacheEntry, TagRegistry
from r12s2cache.tier import LRUTier

BatchItem = tuple[str, Any, float | None, Iterable[str]]
Validator = Callable[[str, Any], bool]


class CacheCoordinator:
    def __init__(self, l1_max_size: int = 4) -> None:
        self.l1 = LRUTier(max_size=l1_max_size)
        self.l2: dict[str, CacheEntry] = {}
        self.registry = TagRegistry()

    def put(
        self,
        key: str,
        value: Any,
        now: float,
        ttl: float | None = None,
        tags: Iterable[str] = (),
    ) -> CacheEntry:
        prior = self.l2.get(key)
        if prior is not None and not prior.is_expired(now):
            version = prior.version + 1
        else:
            version = 1
        expires_at = (now + ttl) if ttl is not None else None
        tag_set = frozenset(tags)
        entry = CacheEntry(
            key=key,
            value=value,
            expires_at=expires_at,
            tags=tag_set,
            version=version,
        )
        self.l2[key] = entry
        self.l1.put(entry, now)
        self.registry.bind(key, tag_set)
        return entry

    def get(self, key: str, now: float) -> Any | None:
        l1_hit = self.l1.get(key, now)
        if l1_hit is not None:
            return l1_hit.value
        l2_hit = self.l2.get(key)
        if l2_hit is None:
            return None
        if l2_hit.is_expired(now):
            del self.l2[key]
            self.registry.unbind(key)
            return None
        self.l1.put(l2_hit, now)
        return l2_hit.value

    def delete(self, key: str) -> bool:
        self.l1.delete(key)
        removed = self.l2.pop(key, None)
        self.registry.unbind(key)
        return removed is not None

    def invalidate_tag(self, tag: str, now: float) -> set[str]:
        keys = self.registry.invalidate_tags([tag])
        for key in keys:
            self.l1.delete(key)
            self.l2.pop(key, None)
        return keys

    def batch_put(
        self,
        items: Sequence[BatchItem],
        now: float,
        validator: Validator | None = None,
    ) -> bool:
        snapshots: dict[str, tuple[CacheEntry | None, bool]] = {}
        l1_order_snapshot = list(self.l1._store.items())
        for key, value, ttl, tags in items:
            if validator is not None and not validator(key, value):
                for snap_key, (old_entry, was_in_l1) in snapshots.items():
                    if old_entry is None:
                        self.delete(snap_key)
                    else:
                        self.l2[snap_key] = old_entry
                        self.registry.bind(snap_key, old_entry.tags)
                self.l1._store.clear()
                for l1_k, l1_entry in l1_order_snapshot:
                    self.l1._store[l1_k] = l1_entry
                return False
            if key not in snapshots:
                snapshots[key] = (self.l2.get(key), key in self.l1)
            self.put(key, value, now=now, ttl=ttl, tags=tags)
        return True

    def query_by_tags(
        self,
        tags: Iterable[str],
        now: float,
        match_all: bool = True,
    ) -> dict[str, Any]:
        tag_list = list(tags)
        if not tag_list:
            return {}
        key_sets = [self.registry.keys_for_tag(t) for t in tag_list]
        if match_all:
            candidates = set.intersection(*key_sets)
        else:
            candidates = set.union(*key_sets)
        results: dict[str, Any] = {}
        for key in sorted(candidates):
            val = self.get(key, now=now)
            if val is not None:
                results[key] = val
        return results
