def _is_int(value):
    return type(value) is int


def _expire(res, t):
    for rid in [rid for rid, item in res.items() if item["exp"] <= t]:
        del res[rid]


def run(ops):
    if type(ops) is not list:
        raise ValueError("ops must be a list")
    stock, res, seq, out = 0, {}, 0, []
    for op in ops:
        if type(op) is not dict:
            raise ValueError("op must be a dict")
        name = op.get("op")
        if name == "init":
            s = op.get("stock")
            if not _is_int(s) or s < 0:
                raise ValueError("bad stock")
            stock, res, seq = s, {}, 0
            out.append(None)
        elif name == "reserve":
            rid, qty, t, ttl = op.get("rid"), op.get("qty"), op.get("t"), op.get("ttl")
            if type(rid) is not str or not _is_int(qty) or qty <= 0 or not _is_int(t) or not _is_int(ttl) or ttl <= 0:
                raise ValueError("bad reserve")
            _expire(res, t)
            if rid in res:
                out.append(False)
                continue
            used = sum(item["qty"] for item in res.values())
            if qty <= stock - used:
                res[rid] = {"qty": qty, "exp": t + ttl, "seq": seq}
                seq += 1
                out.append(True)
            else:
                out.append(False)
        elif name == "release":
            rid, t = op.get("rid"), op.get("t")
            if type(rid) is not str or not _is_int(t):
                raise ValueError("bad release")
            _expire(res, t)
            out.append(rid in res)
            if out[-1]:
                del res[rid]
        elif name == "commit":
            rid, t = op.get("rid"), op.get("t")
            if type(rid) is not str or not _is_int(t):
                raise ValueError("bad commit")
            _expire(res, t)
            out.append(rid in res)
            if out[-1]:
                stock -= res[rid]["qty"]
                del res[rid]
        elif name == "snapshot":
            t = op.get("t")
            if not _is_int(t):
                raise ValueError("bad snapshot")
            _expire(res, t)
            items = [[rid, item["qty"], item["exp"]] for rid, item in res.items()]
            items.sort(key=lambda row: row[0])
            out.append(items)
        else:
            raise ValueError("bad op")
    return out
