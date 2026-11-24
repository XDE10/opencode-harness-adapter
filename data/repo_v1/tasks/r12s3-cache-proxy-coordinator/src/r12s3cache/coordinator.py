from r12s3cache.directives import parse_directive
from r12s3cache.models import CacheEntry


class MultiTierCache:
    def __init__(self, capacity: int, policy: str = "lru", default_ttl: int = 60) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        if policy not in ("lru", "lfu"):
            raise ValueError(f"Unsupported eviction policy: {policy}")
        self.capacity = capacity
        self.policy = policy
        self.default_ttl = default_ttl
        self.l1: dict[str, CacheEntry] = {}
        self.l2: dict[str, CacheEntry] = {}
        self._l1_tags: dict[str, set[str]] = {}

    def _index_tags(self, key: str, tags: frozenset[str]) -> None:
        for tag in tags:
            self._l1_tags.setdefault(tag, set()).add(key)

    def _unindex_tags(self, key: str, tags: frozenset[str]) -> None:
        for tag in tags:
            bucket = self._l1_tags.get(tag)
            if bucket is not None:
                bucket.discard(key)
                if not bucket:
                    del self._l1_tags[tag]

    def _purge_expired_l1(self, now: int) -> None:
        expired_keys = [k for k, entry in self.l1.items() if entry.is_expired(now)]
        for k in expired_keys:
            entry = self.l1.pop(k)
            self._unindex_tags(k, entry.tags)

    def _evict_one_l1(self) -> str:
        candidates = [e for e in self.l1.values() if not e.pinned]
        if not candidates:
            raise RuntimeError("Cache full of pinned entries")
        if self.policy == "lru":
            victim = min(candidates, key=lambda e: (e.last_accessed, e.created_at, e.key))
        else:
            victim = min(candidates, key=lambda e: (e.hits, e.last_accessed, e.key))
        del self.l1[victim.key]
        self._unindex_tags(victim.key, victim.tags)
        return victim.key

    def _admit_l1(self, entry: CacheEntry, now: int) -> None:
        if len(self.l1) >= self.capacity:
            self._evict_one_l1()
        self.l1[entry.key] = entry
        self._index_tags(entry.key, entry.tags)

    def put(self, key: str, value: object, header: str = "", now: int = 0) -> bool:
        directive = parse_directive(header, default_ttl=self.default_ttl)
        if directive.no_store or directive.ttl == 0:
            old_l1 = self.l1.pop(key, None)
            if old_l1 is not None:
                self._unindex_tags(key, old_l1.tags)
            self.l2.pop(key, None)
            return False

        entry = CacheEntry(
            key=key,
            value=value,
            created_at=now,
            expires_at=now + directive.ttl,
            last_accessed=now,
            hits=1,
            tags=directive.tags,
            pinned=directive.pinned,
        )
        self.l2[key] = entry.clone_for_l1(now)
        self._admit_l1(entry, now)
        return True

    def get(self, key: str, now: int = 0) -> object | None:
        entry = self.l1.get(key)
        if entry is not None:
            if entry.is_expired(now):
                del self.l1[key]
                self._unindex_tags(key, entry.tags)
            else:
                entry.hits += 1
                entry.last_accessed = now
                return entry.value

        l2_entry = self.l2.get(key)
        if l2_entry is None:
            return None
        if l2_entry.is_expired(now):
            del self.l2[key]
            return None

        promoted = l2_entry.clone_for_l1(now)
        self._admit_l1(promoted, now)
        return promoted.value

    def invalidate_tag(self, tag: str) -> int:
        removed_keys: set[str] = set()
        l1_keys = list(self._l1_tags.get(tag, ()))
        for k in l1_keys:
            entry = self.l1.pop(k, None)
            if entry is not None:
                self._unindex_tags(k, entry.tags)
                removed_keys.add(k)

        l2_matches = [k for k, e in self.l2.items() if tag in e.tags]
        for k in l2_matches:
            del self.l2[k]
            removed_keys.add(k)

        return len(removed_keys)
