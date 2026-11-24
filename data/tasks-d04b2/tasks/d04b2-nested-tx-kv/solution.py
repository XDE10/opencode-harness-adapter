class TransactionalKV:
    def __init__(self):
        self.store = {}
        self.val_counts = {}
        self.tx_stack = []

    def _inc_count(self, val, delta):
        cur = self.val_counts.get(val, 0) + delta
        if cur <= 0:
            self.val_counts.pop(val, None)
        else:
            self.val_counts[val] = cur

    def _record_undo(self, key):
        if not self.tx_stack:
            return
        top = self.tx_stack[-1]
        if key not in top:
            top[key] = (key in self.store, self.store.get(key))

    def set(self, key, val):
        self._record_undo(key)
        if key in self.store:
            old_val = self.store[key]
            self._inc_count(old_val, -1)
        self.store[key] = val
        self._inc_count(val, 1)

    def delete(self, key):
        if key not in self.store:
            return False
        self._record_undo(key)
        old_val = self.store.pop(key)
        self._inc_count(old_val, -1)
        return True

    def get(self, key):
        val = self.store.get(key)
        return val or None

    def count(self, val):
        return self.val_counts.get(val, 0)

    def begin(self):
        self.tx_stack.append({})
        return len(self.tx_stack)

    def commit(self):
        if not self.tx_stack:
            raise ValueError("No active transaction to commit")
        self.tx_stack.pop()
        return len(self.tx_stack)

    def rollback(self):
        if not self.tx_stack:
            raise ValueError("No active transaction to rollback")
        undo = self.tx_stack.pop()
        for key, (existed, old_val) in undo.items():
            if key in self.store:
                self._inc_count(self.store[key], -1)
            if existed:
                self.store[key] = old_val
                self._inc_count(old_val, 1)
            else:
                self.store.pop(key, None)
        return len(self.tx_stack)


def run_tx_kv(ops):
    kv = TransactionalKV()
    out = []
    for item in ops:
        op = item.get("op")
        if op == "set":
            out.append(kv.set(item["key"], item["val"]))
        elif op == "delete":
            out.append(kv.delete(item["key"]))
        elif op == "get":
            out.append(kv.get(item["key"]))
        elif op == "count":
            out.append(kv.count(item["val"]))
        elif op == "begin":
            out.append(kv.begin())
        elif op == "commit":
            out.append(kv.commit())
        elif op == "rollback":
            out.append(kv.rollback())
        else:
            raise ValueError(f"Unknown op: {op}")
    return out
