Fix `aggregate_tumbling_windows(events, window_ms, allowed_lateness_ms=0)` in `solution.py`.

`events` is a list of dicts, each containing `"ts"` (non-negative `int`), `"key"` (non-empty `str`), and `"delta"` (`int`).
- Raise `ValueError` if `window_ms <= 0` or `allowed_lateness_ms < 0`.
- Missing keys in an event raise `KeyError`; negative `"ts"`, non-int/bool `"ts"` or `"delta"`, or empty `"key"` raises `ValueError`.
- Process `events` in arrival order, validating every event before late-arrival filtering.
- Maintain a global high-watermark `max_ts_seen` (initially `None`). Drop an event if `max_ts_seen is not None` and `ts < max_ts_seen - allowed_lateness_ms` (events with `ts == max_ts_seen - allowed_lateness_ms` are kept). Otherwise accept it and update `max_ts_seen`.
- Assign each accepted event to a fixed tumbling window `[window_start, window_end)` where `window_start = (ts // window_ms) * window_ms` and `window_end = window_start + window_ms`.
- Aggregate per `(window_start, key)` with `count`, `sum`, `min`, and `max` of `"delta"`.
- Return a list of dicts `{"window_start": int, "window_end": int, "key": str, "count": int, "sum": int, "min": int, "max": int}` sorted by `(window_start, key)`.

Example:
```python
aggregate_tumbling_windows(
    [{"ts": 15, "key": "cpu", "delta": 4}, {"ts": 12, "key": "cpu", "delta": 0}],
    window_ms=10,
    allowed_lateness_ms=5,
)
# -> [{"window_start": 10, "window_end": 20, "key": "cpu", "count": 2, "sum": 4, "min": 0, "max": 4}]
```
