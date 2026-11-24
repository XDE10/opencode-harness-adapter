Fix `build_session_windows(events, gap_ms, allowed_lateness_ms=0)` in `solution.py`.

`events` is a list of dicts, each containing `"user"` (non-empty `str`), `"ts"` (non-negative `int`), and `"kind"` (`str`).
- Raise `ValueError` if `gap_ms < 0` or `allowed_lateness_ms < 0`.
- Missing required keys raise `KeyError`. An empty `"user"` or negative `"ts"` raises `ValueError`.
- Scan `events` in arrival order while maintaining a global high-watermark `max_ts_seen` (initially `None`). Before updating `max_ts_seen` with the current event, drop the event if `max_ts_seen is not None` and `ts < max_ts_seen - allowed_lateness_ms`. Note that events with `ts == max_ts_seen - allowed_lateness_ms` are kept.
- Validation of every input event happens before late-arrival filtering.
- Group accepted events by `"user"` and sort each user's events by `(ts, arrival_index)`.
- Partition each user's sorted events into sessions: start a new session whenever `curr_ts - prev_ts > gap_ms` (events separated by exactly `gap_ms` stay in the same session).
- Produce one dict per session:
  `{"user": str, "start_ts": int, "end_ts": int, "duration_ms": int, "event_count": int, "kinds": [str, ...]}`
  where `duration_ms = end_ts - start_ts` and `kinds` preserves the `(ts, arrival_index)` order.
- Return all sessions sorted by `(start_ts, user, end_ts)`.

Example:
```python
build_session_windows(
    [{"user": "u1", "ts": 100, "kind": "view"}, {"user": "u1", "ts": 150, "kind": "click"}],
    gap_ms=50,
)
# -> [{"user": "u1", "start_ts": 100, "end_ts": 150, "duration_ms": 50, "event_count": 2, "kinds": ["view", "click"]}]
```
