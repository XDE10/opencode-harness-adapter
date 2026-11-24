class LFUTTLCache:
    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self.entries = {}
        self.seq = 0

    def _purge(self, t: int) -> None:
        expired = [
            k for k, v in self.entries.items()
            if v["expire_at"] is not None and v["expire_at"] <= t
        ]
        for k in expired:
            del self.entries[k]

    def _evict_one(self) -> None:
        if not self.entries:
            return
        victim = min(
            self.entries.keys(),
            key=lambda k: (self.entries[k]["freq"], self.entries[k]["last_used"]),
        )
        del self.entries[victim]

    def put(self, t: int, key: str, val: int, ttl: int | None = None) -> bool:
        self.seq += 1
        self._purge(t)
        if ttl is not None and ttl <= 0:
            self.entries.pop(key, None)
            return False
        expire_at = None if ttl is None else t + ttl
        if key in self.entries:
            entry = self.entries[key]
            entry["val"] = val
            entry["freq"] += 1
            entry["last_used"] = (t, self.seq)
            entry["expire_at"] = expire_at
            return True
        if len(self.entries) >= self.capacity:
            self._evict_one()
        self.entries[key] = {
            "val": val,
            "freq": 1,
            "last_used": (t, self.seq),
            "expire_at": expire_at,
        }
        return True

    def get(self, t: int, key: str) -> int:
        self.seq += 1
        self._purge(t)
        if key not in self.entries:
            return -1
        entry = self.entries[key]
        entry["freq"] += 1
        entry["last_used"] = (t, self.seq)
        return entry["val"]

    def delete(self, t: int, key: str) -> bool:
        self.seq += 1
        self._purge(t)
        if key in self.entries:
            del self.entries[key]
            return True
        return False

    def snapshot(self, t: int) -> list:
        self._purge(t)
        ordered = sorted(
            self.entries.items(),
            key=lambda item: (-item[1]["freq"], -item[1]["last_used"][0], -item[1]["last_used"][1]),
        )
        return [[k, v["val"], v["freq"]] for k, v in ordered]


def run_lfu_cache(capacity: int, ops: list[dict]) -> list:
    cache = LFUTTLCache(capacity)
    out = []
    for item in ops:
        op = item.get("op")
        t = item["t"]
        if op == "put":
            out.append(cache.put(t, item["key"], item["val"], item.get("ttl")))
        elif op == "get":
            out.append(cache.get(t, item["key"]))
        elif op == "delete":
            out.append(cache.delete(t, item["key"]))
        elif op == "snapshot":
            out.append(cache.snapshot(t))
        else:
            raise ValueError(f"Unknown op: {op}")
    return out
