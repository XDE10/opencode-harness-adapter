from collections import defaultdict, deque


def _validate_record(rec):
    ts = rec["ts"]
    service = rec["service"]
    status = rec["status"]
    if isinstance(ts, bool) or not isinstance(ts, int) or ts < 0:
        raise ValueError("ts must be a non-negative integer")
    if not isinstance(service, str) or not service:
        raise ValueError("service must be a non-empty string")
    if isinstance(status, bool) or not isinstance(status, int):
        raise ValueError("status must be an integer")
    return ts, service, status


def _scan_service(service, items, window_ms, min_events, threshold_pct):
    items.sort(key=lambda item: item[0])
    window = deque()
    error_count = 0
    bursts = []

    for ts, status in items:
        is_err = 1 if status >= 500 else 0
        window.append((ts, is_err))
        error_count += is_err
        while window and window[0][0] <= ts - window_ms:
            _, old_err = window.popleft()
            error_count -= old_err
        total = len(window)
        if total >= min_events and error_count * 100 > total * threshold_pct:
            bursts.append({
                "service": service,
                "ts": ts,
                "errors": error_count,
                "total": total,
            })

    return bursts


def detect_error_bursts(records, window_ms, min_events, threshold_pct):
    if window_ms < 0 or min_events <= 0 or threshold_pct < 0 or threshold_pct > 100:
        raise ValueError("invalid window or threshold parameters")

    by_service = defaultdict(list)
    for rec in records:
        ts, service, status = _validate_record(rec)
        by_service[service].append((ts, status))

    bursts = []
    for service, items in by_service.items():
        bursts.extend(_scan_service(service, items, window_ms, min_events, threshold_pct))

    bursts.sort(key=lambda b: (b["ts"], b["service"]))
    return bursts
