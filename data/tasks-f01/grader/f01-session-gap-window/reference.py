from collections import defaultdict


def _validate_event(event):
    user = event["user"]
    ts = event["ts"]
    kind = event["kind"]
    if not isinstance(user, str) or not user:
        raise ValueError("user must be a non-empty string")
    if isinstance(ts, bool) or not isinstance(ts, int) or ts < 0:
        raise ValueError("ts must be a non-negative integer")
    if not isinstance(kind, str):
        raise ValueError("kind must be a string")
    return user, ts, kind


def _split_user_sessions(user, items, gap_ms):
    items.sort(key=lambda item: (item[0], item[1]))
    sessions = []
    cur_start = items[0][0]
    cur_end = items[0][0]
    kinds = [items[0][2]]

    for ts, _idx, kind in items[1:]:
        if ts - cur_end > gap_ms:
            sessions.append({
                "user": user,
                "start_ts": cur_start,
                "end_ts": cur_end,
                "duration_ms": cur_end - cur_start,
                "event_count": len(kinds),
                "kinds": kinds,
            })
            cur_start = ts
            cur_end = ts
            kinds = [kind]
        else:
            cur_end = ts
            kinds.append(kind)

    sessions.append({
        "user": user,
        "start_ts": cur_start,
        "end_ts": cur_end,
        "duration_ms": cur_end - cur_start,
        "event_count": len(kinds),
        "kinds": kinds,
    })
    return sessions


def build_session_windows(events, gap_ms, allowed_lateness_ms=0):
    if gap_ms < 0 or allowed_lateness_ms < 0:
        raise ValueError("gap_ms and allowed_lateness_ms must be non-negative")

    by_user = defaultdict(list)
    max_ts_seen = None

    for idx, event in enumerate(events):
        user, ts, kind = _validate_event(event)
        if max_ts_seen is not None and ts < max_ts_seen - allowed_lateness_ms:
            continue
        if max_ts_seen is None or ts > max_ts_seen:
            max_ts_seen = ts
        by_user[user].append((ts, idx, kind))

    sessions = []
    for user, items in by_user.items():
        sessions.extend(_split_user_sessions(user, items, gap_ms))

    sessions.sort(key=lambda s: (s["start_ts"], s["user"], s["end_ts"]))
    return sessions
