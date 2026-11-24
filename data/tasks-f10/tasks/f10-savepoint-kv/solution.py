import copy


class SavepointKV:
    def __init__(self):
        self.base = {}
        self.in_txn = False
        self.txn_store = None
        self.savepoints = []

    def _active(self):
        return self.txn_store if self.in_txn else self.base

    def _find_sp(self, name):
        for i in range(len(self.savepoints) - 1, -1, -1):
            if self.savepoints[i][0] == name:
                return i
        raise KeyError(name)

    def begin(self):
        if self.in_txn:
            raise ValueError("transaction already active")
        self.in_txn = True
        self.txn_store = copy.deepcopy(self.base)
        self.savepoints = []
        return True

    def savepoint(self, name):
        if not self.in_txn:
            raise ValueError("no active transaction")
        self.savepoints.append((name, copy.deepcopy(self.txn_store)))
        return len(self.savepoints)

    def rollback_to(self, name):
        if not self.in_txn:
            raise ValueError("no active transaction")
        idx = self._find_sp(name)
        self.txn_store = self.savepoints[idx][1]
        self.savepoints = self.savepoints[:idx]
        return len(self.savepoints)

    def release(self, name):
        if not self.in_txn:
            raise ValueError("no active transaction")
        idx = self._find_sp(name)
        self.savepoints = self.savepoints[:idx]
        return len(self.savepoints)

    def commit(self):
        if not self.in_txn:
            raise ValueError("no active transaction")
        self.base = self.txn_store
        self.txn_store = None
        self.in_txn = False
        self.savepoints = []
        return len(self.base)

    def rollback(self):
        if not self.in_txn:
            raise ValueError("no active transaction")
        self.txn_store = None
        self.in_txn = False
        self.savepoints = []
        return len(self.base)

    def set(self, key, value):
        if value is None:
            raise ValueError("value cannot be None")
        self._active()[key] = value
        return value

    def delete(self, key):
        active = self._active()
        if key not in active:
            raise KeyError(key)
        del active[key]
        return True

    def get(self, key, default=None):
        return self._active().get(key) or default

    def snapshot(self):
        active = self._active()
        return {k: copy.deepcopy(active[k]) for k in sorted(active)}


def run(ops):
    kv = SavepointKV()
    out = []
    for item in ops:
        op = item.get("op")
        if op == "begin":
            out.append(kv.begin())
        elif op == "savepoint":
            out.append(kv.savepoint(item["name"]))
        elif op == "rollback_to":
            out.append(kv.rollback_to(item["name"]))
        elif op == "release":
            out.append(kv.release(item["name"]))
        elif op == "commit":
            out.append(kv.commit())
        elif op == "rollback":
            out.append(kv.rollback())
        elif op == "set":
            out.append(kv.set(item["key"], item["value"]))
        elif op == "delete":
            out.append(kv.delete(item["key"]))
        elif op == "get":
            out.append(kv.get(item["key"], item.get("default")))
        elif op == "snapshot":
            out.append(kv.snapshot())
        else:
            raise ValueError(f"unknown op: {op}")
    return out
