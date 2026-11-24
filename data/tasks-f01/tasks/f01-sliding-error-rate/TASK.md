Fix `detect_error_bursts(records, window_ms, min_events, threshold_pct)` in `solution.py`.

`records` is a list of dicts, each containing `"ts"` (non-negative `int`), `"service"` (non-empty `str`), and `"status"` (`int`).
- Raise `ValueError` if `window_ms < 0`, `min_events <= 0`, or `threshold_pct < 0 or threshold_pct > 100`.
- Missing keys in a record raise `KeyError`; negative `"ts"`, empty `"service"`, or non-int/bool `"ts"`/`"status"` raises `ValueError`.
- Group records by `"service"` and evaluate each service at every distinct timestamp `ts` present for that service.
- At timestamp `ts`, consider all records for that service whose timestamp `t` falls in the inclusive window `[ts - window_ms, ts]`.
- Let `total` be the number of records in `[ts - window_ms, ts]` and `errors` be the number of those records with `status >= 500`.
- Emit a burst entry `{"service": str, "ts": int, "errors": int, "total": int}` whenever `total >= min_events` and `errors * 100 >= total * threshold_pct`.
- Return all emitted burst entries sorted by `(ts, service)`.

Example:
```python
detect_error_bursts(
    [
        {"ts": 100, "service": "auth", "status": 500},
        {"ts": 110, "service": "auth", "status": 200},
    ],
    window_ms=10,
    min_events=2,
    threshold_pct=50,
)
# -> [{"service": "auth", "ts": 110, "errors": 1, "total": 2}]
```
