_MISSING = object()
_TOMB = object()


class MVCCStore:
    def __init__(self):
        self.ver = 0
        self.versions = {}
        self.active = {}

    def _committed_at(self, key, at_ver):
        history = self.versions.get(key, ())
        val = _MISSING
        for v, stored in history:
            if v <= at_ver:
                val = stored
            else:
                break
        return val

    def begin(self, tx):
        if tx in self.active:
            raise ValueError(f"tx already active: {tx}")
        self.active[tx] = {"snap": self.ver, "writes": {}}
        return self.ver

    def write(self, tx, key, value):
        if value is None:
            raise ValueError("value cannot be None")
        if tx not in self.active:
            raise KeyError(tx)
        self.active[tx]["writes"][key] = value
        return value

    def delete(self, tx, key):
        if tx not in self.active:
            raise KeyError(tx)
        state = self.active[tx]
        if key in state["writes"]:
            cur = state["writes"][key]
        else:
            cur = self._committed_at(key, state["snap"])
        if cur is _MISSING or cur is _TOMB:
            raise KeyError(key)
        state["writes"][key] = _TOMB
        return True

    def read(self, tx, key, default=None):
        if tx not in self.active:
            raise KeyError(tx)
        state = self.active[tx]
        if key in state["writes"]:
            val = state["writes"][key]
        else:
            val = self._committed_at(key, state["snap"])
        if val is _MISSING or val is _TOMB:
            return default
        return val if val else default

    def commit(self, tx):
        if tx not in self.active:
            raise KeyError(tx)
        state = self.active[tx]
        snap = state["snap"]
        for key in state["writes"]:
            history = self.versions.get(key)
            if history and history[-1][0] >= snap:
                raise ValueError(f"write-write conflict on {key}")
        self.active.pop(tx)
        self.ver += 1
        for key, val in state["writes"].items():
            self.versions.setdefault(key, []).append((self.ver, val))
        return self.ver

    def abort(self, tx):
        if tx not in self.active:
            raise KeyError(tx)
        self.active.pop(tx)
        return True

    def committed_keys(self, at_ver=None):
        target = self.ver if at_ver is None else at_ver
        out = []
        for key in sorted(self.versions):
            val = self._committed_at(key, target)
            if val is not _MISSING and val is not _TOMB:
                out.append(key)
        return out


def run(ops):
    store = MVCCStore()
    out = []
    for item in ops:
        op = item.get("op")
        if op == "begin":
            out.append(store.begin(item["tx"]))
        elif op == "write":
            out.append(store.write(item["tx"], item["key"], item["value"]))
        elif op == "delete":
            out.append(store.delete(item["tx"], item["key"]))
        elif op == "read":
            out.append(store.read(item["tx"], item["key"], item.get("default")))
        elif op == "commit":
            out.append(store.commit(item["tx"]))
        elif op == "abort":
            out.append(store.abort(item["tx"]))
        elif op == "committed_keys":
            out.append(store.committed_keys(item.get("at_ver")))
        else:
            raise ValueError(f"unknown op: {op}")
    return out
