def _validate(series_list, blackouts, horizon):
    if len(horizon) != 2 or horizon[0] < 0 or horizon[1] <= horizon[0]:
        raise ValueError("Invalid horizon")
    for b in blackouts:
        if len(b) != 2 or b[0] < 0 or b[1] <= b[0]:
            raise ValueError("Invalid blackout interval")
    seen = set()
    for s in series_list:
        name = s["name"]
        if name in seen:
            raise ValueError(f"Duplicate series name: {name}")
        seen.add(name)
        if (
            s["start"] < 0
            or s["duration"] <= 0
            or s["step"] <= 0
            or s["count"] < 1
            or s["min_chunk"] < 1
        ):
            raise ValueError(f"Invalid parameters for series {name}")


def _merge_intervals(intervals):
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda x: (x[0], x[1]))
    merged = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1][1] = end
        else:
            merged.append([start, end])
    return merged


def _subtract_blackouts(start, end, merged_blackouts):
    fragments = [[start, end]]
    for b_start, b_end in merged_blackouts:
        next_fragments = []
        for f_start, f_end in fragments:
            if b_end <= f_start or b_start >= f_end:
                next_fragments.append([f_start, f_end])
            else:
                if f_start < b_start:
                    next_fragments.append([f_start, b_start])
                if b_end < f_end:
                    next_fragments.append([b_end, f_end])
        fragments = next_fragments
    return fragments


def _compute_conflicts(slots):
    points = sorted({pt for s, e, _ in slots for pt in (s, e)})
    raw_conflicts = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        active = sorted(name for s, e, name in slots if s <= a and b <= e)
        if len(active) >= 2:
            raw_conflicts.append([a, b, active])

    merged = []
    for seg_start, seg_end, names in raw_conflicts:
        if merged and merged[-1][1] == seg_start and merged[-1][2] == names:
            merged[-1][1] = seg_end
        else:
            merged.append([seg_start, seg_end, names])
    return merged


def build_schedule(series_list, blackouts, horizon):
    _validate(series_list, blackouts, horizon)
    h_start, h_end = horizon
    merged_blackouts = _merge_intervals(blackouts)
    all_slots = []

    for s in series_list:
        name = s["name"]
        min_chunk = s["min_chunk"]
        kept = []
        for k in range(s["count"]):
            occ_start = max(s["start"] + k * s["step"], h_start)
            occ_end = min(s["start"] + k * s["step"] + s["duration"], h_end)
            if occ_start >= occ_end:
                continue
            for f_start, f_end in _subtract_blackouts(occ_start, occ_end, merged_blackouts):
                if f_end - f_start > min_chunk:
                    kept.append([f_start, f_end])
        for m_start, m_end in _merge_intervals(kept):
            all_slots.append([m_start, m_end, name])

    all_slots.sort(key=lambda x: (x[0], x[1], x[2]))
    return {"slots": all_slots, "conflicts": _compute_conflicts(all_slots)}
