def _check_bounds(l, r):
    if type(l) is not int or type(r) is not int or l > r:
        raise ValueError("bad interval")


def _add(intervals, l, r):
    out = []
    ns, nr = l, r
    for s, e in intervals:
        if e + 1 < ns:
            out.append([s, e])
        elif nr + 1 < s:
            out.append([ns, nr])
            ns, nr = s, e
        else:
            ns = min(ns, s)
            nr = max(nr, e)
    out.append([ns, nr])
    return out


def _remove(intervals, l, r):
    out = []
    for s, e in intervals:
        if e < l or r < s:
            out.append([s, e])
            continue
        if s < l:
            out.append([s, l - 1])
        if r < e:
            out.append([r + 1, e])
    return out


def _query(intervals, l, r):
    found = []
    for s, e in intervals:
        if e < l:
            continue
        if s > r:
            break
        found.append([max(s, l), min(e, r)])
    return found


def run(ops):
    if type(ops) is not list:
        raise ValueError("ops must be a list")
    intervals = []
    results = []
    for op in ops:
        if type(op) is not dict:
            raise ValueError("op must be a dict")
        name = op.get("op")
        if name not in ("add", "remove", "query"):
            raise ValueError("unknown op")
        if "l" not in op or "r" not in op:
            raise ValueError("missing bounds")
        l, r = op["l"], op["r"]
        _check_bounds(l, r)
        if name == "add":
            intervals = _add(intervals, l, r)
            results.append(None)
        elif name == "remove":
            intervals = _remove(intervals, l, r)
            results.append(None)
        else:
            results.append(_query(intervals, l, r))
    return results
