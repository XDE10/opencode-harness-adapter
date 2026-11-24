def _is_int(value):
    return type(value) is int


def _validate(events, idle_gap, threshold):
    if not _is_int(idle_gap) or idle_gap < 1:
        raise ValueError
    if not _is_int(threshold):
        raise ValueError
    if not isinstance(events, list):
        raise ValueError
    required = {"user", "t", "seq", "value"}
    for event in events:
        if not isinstance(event, dict) or set(event) != required:
            raise ValueError
        if not isinstance(event["user"], str):
            raise ValueError
        if not _is_int(event["t"]) or not _is_int(event["seq"]) or not _is_int(event["value"]):
            raise ValueError


def _is_anomaly(value, threshold):
    return value >= threshold


def analyze_sessions(events, idle_gap, threshold):
    _validate(events, idle_gap, threshold)
    grouped = {}
    for index, event in enumerate(events):
        grouped.setdefault(event["user"], []).append(
            (event["t"], event["seq"], index, event["value"])
        )
    result = {}
    for user in sorted(grouped):
        rows = sorted(grouped[user], key=lambda row: (row[0], row[1], row[2]))
        sessions = []
        current = None
        previous_t = None
        streak = 0
        for t, _seq, _index, value in rows:
            if current is None or t - previous_t > idle_gap:
                if current is not None:
                    sessions.append(current)
                streak = 1 if _is_anomaly(value, threshold) else 0
                current = {
                    "start": t,
                    "end": t,
                    "count": 1,
                    "max_streak": streak,
                    "peak": value,
                }
            else:
                current["end"] = t
                current["count"] += 1
                if value > current["peak"]:
                    current["peak"] = value
                streak = streak + 1 if _is_anomaly(value, threshold) else 0
                if streak > current["max_streak"]:
                    current["max_streak"] = streak
            previous_t = t
        if current is not None:
            sessions.append(current)
        result[user] = sessions
    return result
