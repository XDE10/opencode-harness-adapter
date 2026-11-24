def _check_range(lo, hi):
    if lo > hi:
        raise ValueError("empty range")


def _add(intervals, lo, hi):
    intervals.append([lo, hi])
    intervals.sort(key=lambda pair: pair[0])
    merged = []
    for start, end in intervals:
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        elif end > merged[-1][1]:
            merged[-1][1] = end
    intervals[:] = merged


def _remove(intervals, lo, hi):
    kept = []
    for start, end in intervals:
        if end < lo or start > hi:
            kept.append([start, end])
            continue
        if start < lo:
            kept.append([start, lo - 1])
        if end > hi:
            kept.append([hi + 1, end])
    intervals[:] = kept


def _query(intervals, lo, hi):
    found = []
    for start, end in intervals:
        if end < lo:
            continue
        if start > hi:
            break
        found.append([max(start, lo), min(end, hi)])
    return found


def _contains(intervals, x):
    for start, end in intervals:
        if x < start:
            return False
        if x <= end:
            return True
    return False


def run(ops):
    intervals = []
    results = []
    for op in ops:
        kind = op["op"]
        if kind in ("add", "remove", "query"):
            lo = op["lo"]
            hi = op["hi"]
            _check_range(lo, hi)
            if kind == "add":
                _add(intervals, lo, hi)
                results.append(None)
            elif kind == "remove":
                _remove(intervals, lo, hi)
                results.append(None)
            else:
                results.append(_query(intervals, lo, hi))
        elif kind == "contains":
            results.append(_contains(intervals, op["x"]))
        elif kind == "reset":
            intervals.clear()
            results.append(None)
        else:
            raise ValueError("unknown op")
    return results
