from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from tiercache.directives import CachePolicy


@dataclass
class CacheEntry:
    key: str
    value: Any
    expires_at: int
    tags: frozenset[str]


class TierStore:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self._tag_index: dict[str, set[str]] = {}

    def __len__(self) -> int:
        return len(self._entries)

    def _remove_key(self, key: str) -> None:
        entry = self._entries.pop(key, None)
        if entry is None:
            return
        for tag in entry.tags:
            bucket = self._tag_index.get(tag)
            if bucket is not None:
                bucket.discard(key)
                if not bucket:
                    del self._tag_index[tag]

    def purge_expired(self, now: int) -> list[str]:
        expired = [k for k, entry in self._entries.items() if entry.expires_at <= now]
        for k in expired:
            self._remove_key(k)
        return expired

    def get(self, key: str, now: int) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= now:
            self._remove_key(key)
            return None
        self._entries.move_to_end(key)
        return entry.value

    def put(self, key: str, value: Any, policy: CachePolicy, now: int) -> bool:
        if policy.no_store or policy.ttl == 0:
            self._remove_key(key)
            return False

        self.purge_expired(now)

        if key in self._entries:
            self._remove_key(key)
        elif len(self._entries) >= self.capacity:
            oldest_key, _ = next(iter(self._entries.items()))
            self._remove_key(oldest_key)

        entry = CacheEntry(
            key=key,
            value=value,
            expires_at=now + policy.ttl,
            tags=policy.tags,
        )
        self._entries[key] = entry
        for tag in policy.tags:
            self._tag_index.setdefault(tag, set()).add(key)
        return True

    def invalidate_tag(self, tag: str) -> list[str]:
        norm_tag = tag.strip().lower()
        keys = sorted(self._tag_index.get(norm_tag, set()))
        for k in keys:
            self._remove_key(k)
        return keys
