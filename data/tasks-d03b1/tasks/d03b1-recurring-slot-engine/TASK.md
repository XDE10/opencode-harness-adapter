Fix `run_recurring_schedule(horizon, ops)` in `solution.py`.

Implement a stateful recurring slot scheduler over a time horizon `[0, horizon)`.
- `horizon`: positive integer (`>= 1`). Raise `ValueError` if `horizon < 1`.
- All intervals are half-open `[s, e)` clipped to `[0, horizon)`.
- `ops`: list of operation dicts executed in order, producing one output entry per operation:
  1. `{"op": "add_series", "id": str, "start": int, "duration": int, "period": int, "count": int}`:
     - Validate that `id` is not currently active, `start >= 0`, `duration >= 1`, `period >= duration`, and `count >= 1`; otherwise raise `ValueError`.
     - Generate occurrence intervals `k = 0, 1, ..., count - 1`: raw interval `[start + k * period, start + k * period + duration)`.
     - Clip each occurrence to `[0, horizon)`: if `raw_start >= horizon`, ignore it; otherwise its clipped interval is `[raw_start, min(raw_end, horizon))`.
     - If no occurrence falls within `[0, horizon)` (empty clipped list), raise `ValueError`.
     - Check whether any generated occurrence overlaps (`max(a, c) < min(b, d)`) any active occurrence of any existing series (excluding occurrences in `exception_set` of existing series).
     - Remember that this transaction is **atomic**: if any occurrence conflicts with an active occurrence, do **not** add the series and append `False`; otherwise store the series and append `True`.
  2. `{"op": "skip_occurrence", "id": str, "index": int}`:
     - Marks occurrence `index` (`0 <= index < count`) of active series `id` as skipped (removed from active occurrences, freeing its time slot).
     - Raise `ValueError` if `id` is not an active series or `index` is out of bounds (`index < 0` or `index >= count`).
     - If occurrence `index` fell within `[0, horizon)` and was not already skipped, mark it skipped and append `True`; if it was already skipped or started at `>= horizon`, append `False`.
  3. `{"op": "remove_series", "id": str}`:
     - If `id` is an active series, delete it (and all its skip state) so `id` can be added again later, and append `True`; otherwise append `False`.
  4. `{"op": "query_window", "start": int, "end": int}`:
     - Validate `0 <= start < end <= horizon`; otherwise raise `ValueError`.
     - Find all currently active (non-skipped) occurrences `[occ_s, occ_e)` across all active series that overlap `[start, end)`.
     - Clip each overlapping occurrence to `[start, end)`: `[max(occ_s, start), min(occ_e, end))`.
     - Return a list `[ [clipped_start, clipped_end, series_id], ... ]` sorted by `(clipped_start, clipped_end, series_id)`.

Example:
```python
run_recurring_schedule(50, [
    {"op": "add_series", "id": "s1", "start": 5, "duration": 10, "period": 20, "count": 3},
    {"op": "skip_occurrence", "id": "s1", "index": 1},
    {"op": "add_series", "id": "s2", "start": 25, "duration": 10, "period": 20, "count": 1},
    {"op": "query_window", "start": 0, "end": 50},
])
# Returns: [True, True, True, [[5, 15, "s1"], [25, 35, "s2"], [45, 50, "s1"]]]
```
