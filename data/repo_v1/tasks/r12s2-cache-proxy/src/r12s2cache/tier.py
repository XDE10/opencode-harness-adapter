from collections import OrderedDict
from r12s2cache.registry import CacheEntry


class LRUTier:
    def __init__(self, max_size: int = 4) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        self.max_size = max_size
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, key: str) -> bool:
        return key in self._store

    def peek(self, key: str) -> CacheEntry | None:
        return self._store.get(key)

    def delete(self, key: str) -> CacheEntry | None:
        return self._store.pop(key, None)

    def purge_expired(self, now: float) -> list[str]:
        expired = [k for k, entry in self._store.items() if entry.is_expired(now)]
        for k in expired:
            del self._store[k]
        return expired

    def get(self, key: str, now: float) -> CacheEntry | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired(now):
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return entry

    def put(self, entry: CacheEntry, now: float) -> list[str]:
        self.purge_expired(now)
        if entry.is_expired(now):
            self._store.pop(entry.key, None)
            return []
        self._store[entry.key] = entry
        self._store.move_to_end(entry.key)
        evicted: list[str] = []
        while len(self._store) > self.max_size:
            old_key, _ = self._store.popitem(last=False)
            evicted.append(old_key)
        return evicted
