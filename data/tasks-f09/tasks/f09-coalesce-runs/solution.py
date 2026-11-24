def _is_strict_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_runs(runs):
    parsed = []
    prev_start = None
    for row in runs:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise ValueError("each run must be a 3-element [start, end, weight]")
        start, end, weight = row
        if not (_is_strict_int(start) and _is_strict_int(end) and _is_strict_int(weight)):
            raise ValueError("start, end, and weight must be integers")
        if start > end:
            raise ValueError("run start cannot exceed end")
        if prev_start is not None and start < prev_start:
            raise ValueError("runs must be ordered by non-decreasing start")
        prev_start = start
        parsed.append((start, end, weight))
    return parsed


def coalesce_runs(runs, max_gap=0, min_weight=None):
    if not _is_strict_int(max_gap) or max_gap < 0:
        raise ValueError("max_gap must be a non-negative integer")
    if min_weight is not None and not _is_strict_int(min_weight):
        raise ValueError("min_weight must be None or an integer")

    parsed = _validate_runs(runs)
    if not parsed:
        return []

    merged = []
    cur_start, cur_end, cur_weight = parsed[0]
    for start, end, weight in parsed[1:]:
        if start - cur_end < max_gap:
            cur_end = end
            cur_weight += weight
        else:
            merged.append([cur_start, cur_end, cur_weight])
            cur_start, cur_end, cur_weight = start, end, weight
    merged.append([cur_start, cur_end, cur_weight])

    if min_weight:
        merged = [item for item in merged if item[2] >= min_weight]
    return merged
