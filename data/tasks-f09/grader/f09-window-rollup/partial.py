_VALID_AGGS = ("sum", "min", "max", "first", "last", "span")


def _is_strict_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _aggregate(window, agg):
    if agg == "sum":
        return sum(window)
    if agg == "min":
        return min(window)
    if agg == "max":
        return max(window)
    if agg == "first":
        return window[0]
    if agg == "last":
        return window[-1]
    return max(window) - min(window)


def windowed_rollup(seq, size, step=1, agg="sum", pad=None, partial=False):
    step = step or 1
    if not _is_strict_int(size) or size < 1:
        raise ValueError("size must be a positive integer")
    if not _is_strict_int(step) or step < 1:
        raise ValueError("step must be a positive integer")
    if pad is not None and not _is_strict_int(pad):
        raise ValueError("pad must be None or an integer")
    if agg not in _VALID_AGGS:
        raise ValueError(f"unsupported aggregation: {agg}")

    values = list(seq)
    for item in values:
        if not _is_strict_int(item):
            raise ValueError("sequence items must be integers")

    n = len(values)
    if n == 0:
        return []

    out = []
    for idx in range(0, n, step):
        window = values[idx:idx + size]
        if len(window) < size:
            if pad is not None:
                window = window + [pad] * (size - len(window))
            elif not partial:
                break
        out.append(_aggregate(window, agg))
    return out
