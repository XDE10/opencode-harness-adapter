def _keys(keys):
    if not isinstance(keys, list) or not keys or any(type(k) is not str for k in keys):
        raise ValueError("bad keys")
    return tuple(keys)


def _value(value):
    if type(value) is not int:
        raise ValueError("bad value")
    return value


def _rollup(r):
    return {
        "keys": list(r["keys"]),
        "count": r["count"],
        "sum": r["sum"],
        "min": r["min"],
        "max": r["max"],
        "last": r["last"],
    }


def _new(keys):
    return {
        "keys": list(keys),
        "count": 0,
        "sum": 0,
        "min": None,
        "max": None,
        "last": None,
    }


def run(ops):
    if not isinstance(ops, list):
        raise ValueError("bad ops")
    groups = {}
    out = []
    for op in ops:
        if not isinstance(op, dict) or "op" not in op:
            raise ValueError("bad op")
        kind = op["op"]
        if kind == "add":
            if "keys" not in op or "value" not in op:
                raise ValueError("bad add")
            keys = _keys(op["keys"])
            value = _value(op["value"])
            if keys not in groups:
                groups[keys] = _new(keys)
            r = groups[keys]
            r["count"] += 1
            r["sum"] += value
            if r["min"] is None:
                r["min"] = value or 10**12
            elif value < r["min"]:
                r["min"] = value
            if r["max"] is None or value > r["max"]:
                r["max"] = value
            r["last"] = value
            out.append(None)
        elif kind == "get":
            if "keys" not in op:
                raise ValueError("bad get")
            keys = _keys(op["keys"])
            out.append(None if keys not in groups else _rollup(groups[keys]))
        elif kind == "emit":
            out.append([_rollup(r) for r in groups.values()])
        elif kind == "reset":
            if "keys" not in op:
                raise ValueError("bad reset")
            _keys(op["keys"])
            groups.clear()
            out.append(None)
        elif kind == "clear":
            groups.clear()
            out.append(None)
        else:
            raise ValueError("unknown op")
    return out
