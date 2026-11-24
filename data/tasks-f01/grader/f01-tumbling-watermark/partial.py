def _parse_event(event):
    ts = event["ts"]
    key = event["key"]
    delta = event["delta"]
    if isinstance(ts, bool) or not isinstance(ts, int) or ts < 0:
        raise ValueError("ts must be a non-negative integer")
    if not isinstance(key, str) or not key:
        raise ValueError("key must be a non-empty string")
    if isinstance(delta, bool) or not isinstance(delta, int):
        raise ValueError("delta must be an integer")
    return ts, key, delta


def _update_bucket(buckets, window_start, window_end, key, delta):
    bucket_key = (window_start, key)
    if bucket_key not in buckets:
        buckets[bucket_key] = {
            "window_start": window_start,
            "window_end": window_end,
            "key": key,
            "count": 1,
            "sum": delta,
            "min": delta,
            "max": delta,
        }
        return
    entry = buckets[bucket_key]
    entry["count"] += 1
    entry["sum"] += delta
    entry["min"] = min(entry["min"], delta)
    entry["max"] = max(entry["max"], delta)


def aggregate_tumbling_windows(events, window_ms, allowed_lateness_ms=0):
    if window_ms <= 0 or allowed_lateness_ms < 0:
        raise ValueError("invalid window_ms or allowed_lateness_ms")

    buckets = {}
    max_ts_seen = None

    for event in events:
        ts, key, delta = _parse_event(event)
        if max_ts_seen is not None and ts < max_ts_seen - allowed_lateness_ms:
            continue
        if max_ts_seen is None or ts > max_ts_seen:
            max_ts_seen = ts
        window_start = (ts // window_ms) * window_ms
        window_end = window_start + window_ms
        _update_bucket(buckets, window_start, window_end, key, delta)

    results = list(buckets.values())
    results.sort(key=lambda r: (r["window_start"], -r["sum"], r["key"]))
    return results
