class WriteBackBuffer:
    def __init__(self, max_dirty: int):
        if max_dirty < 1:
            raise ValueError("max_dirty must be >= 1")
        self.max_dirty = max_dirty
        self.store = {}
        self.buffer = {}

    def _purge(self, t: int) -> None:
        expired = [
            k for k, v in self.buffer.items()
            if v["expire_at"] is not None and v["expire_at"] < t
        ]
        for k in expired:
            del self.buffer[k]

    def _dirty_keys(self) -> list[str]:
        return [k for k, v in self.buffer.items() if v["dirty"]]

    def _evict_oldest_dirty(self) -> None:
        dirty = self._dirty_keys()
        if not dirty:
            return
        victim = min(dirty, key=lambda k: (self.buffer[k]["updated_at"], k))
        self.store[victim] = self.buffer[victim]["val"]
        self.buffer[victim]["dirty"] = False

    def write(self, t: int, key: str, val: int, ttl: int | None) -> None:
        self._purge(t)
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be positive")
        if len(self._dirty_keys()) >= self.max_dirty:
            self._evict_oldest_dirty()
        expire_at = None if ttl is None else t + ttl
        self.buffer[key] = {
            "val": val,
            "dirty": True,
            "updated_at": t,
            "expire_at": expire_at,
        }
        return None

    def read(self, t: int, key: str) -> int | None:
        self._purge(t)
        if key in self.buffer:
            return self.buffer[key]["val"]
        if key in self.store:
            val = self.store[key]
            self.buffer[key] = {
                "val": val,
                "dirty": False,
                "updated_at": t,
                "expire_at": None,
            }
            return val
        return None

    def flush(self, t: int) -> int:
        self._purge(t)
        count = 0
        for k, entry in self.buffer.items():
            if entry["dirty"]:
                self.store[k] = entry["val"]
                entry["dirty"] = False
                count += 1
        return count

    def rollback(self, t: int) -> int:
        self._purge(t)
        dirty = self._dirty_keys()
        for k in dirty:
            if k in self.store:
                self.buffer[k]["val"] = self.store[k]
            else:
                del self.buffer[k]
        return len(dirty)

    def status(self, t: int) -> dict:
        self._purge(t)
        return {
            "dirty": sorted(self._dirty_keys()),
            "store": [[k, self.store[k]] for k in sorted(self.store.keys())],
        }


def run(max_dirty: int, ops: list[dict]) -> list:
    wb = WriteBackBuffer(max_dirty)
    out = []
    for item in ops:
        op = item.get("op")
        t = item["t"]
        if op == "write":
            out.append(wb.write(t, item["key"], item["val"], item.get("ttl")))
        elif op == "read":
            out.append(wb.read(t, item["key"]))
        elif op == "flush":
            out.append(wb.flush(t))
        elif op == "rollback":
            out.append(wb.rollback(t))
        elif op == "status":
            out.append(wb.status(t))
        else:
            raise ValueError(f"Unknown op: {op}")
    return out
