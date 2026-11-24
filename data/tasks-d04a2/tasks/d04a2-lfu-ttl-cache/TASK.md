Fix `run_lfu_cache(capacity, ops)` in `solution.py`.

Implement a deterministic LFU (Least Frequently Used) cache with optional TTL expiration and recency tie-breaking, driven by integer timestamps `t`.

### Parameters
- `capacity`: integer (`>= 1`). Raise `ValueError` if `capacity < 1`.
- `ops`: list of operation dicts processed sequentially in non-decreasing timestamp `t` order.

### Entry State & Eviction Rules
Before executing any operation at timestamp `t`, first purge all entries that have a non-`None` expiration timestamp `expire_at <= t`.

Each active entry tracks:
- `val`: integer value
- `freq`: positive integer access count
- `last_used`: tuple `(t, seq)` representing the timestamp and monotonic operation sequence number of its most recent `put` or `get`
- `expire_at`: integer timestamp or `None`

When inserting a **new** key into a full cache (after purging expired entries at `t`), evict the entry with the lowest `freq`, breaking ties by the smallest `last_used` (least recently used).

### Operations
1. `{"op": "put", "t": int, "key": str, "val": int, "ttl": int | None}` (if `"ttl"` is omitted, treat it as `None`):
   - Purge expired entries at `t`.
   - If `ttl is not None` and `ttl <= 0`: if `key` is currently in the cache, delete it; do not insert anything, and append `False` to results.
   - If `key` is already present (and not expired): update its `val`, increment its `freq` by `1`, update `last_used` to the current operation, and replace its `expire_at` with `None if ttl is None else t + ttl`. Append `True`.
   - If `key` is not present: if the cache is at `capacity`, evict one entry according to the LFU+LRU rule. Insert `key` with `val`, `freq = 1`, current `last_used`, and `expire_at = None if ttl is None else t + ttl`. Append `True`.
2. `{"op": "get", "t": int, "key": str}`:
   - Purge expired entries at `t`.
   - If `key` is present, increment its `freq` by `1`, update `last_used` to the current operation, and append its `val`. (Does not alter `expire_at`.)
   - Otherwise, append `-1`.
3. `{"op": "delete", "t": int, "key": str}`:
   - Purge expired entries at `t`.
   - If `key` is present, remove it and append `True`; otherwise append `False`.
4. `{"op": "snapshot", "t": int}`:
   - Purge expired entries at `t` without altering `freq` or `last_used`.
   - Append a list of `[key, val, freq]` lists for all active entries, ordered from highest `freq` to lowest `freq`, breaking ties from most recently used (largest `last_used`) to least recently used.
5. Any unknown `"op"` must raise `ValueError`.

### Example
```python
run_lfu_cache(2, [
    {"op": "put", "t": 1, "key": "a", "val": 10, "ttl": 5},
    {"op": "put", "t": 2, "key": "b", "val": 20, "ttl": None},
    {"op": "get", "t": 3, "key": "a"},
    {"op": "put", "t": 4, "key": "c", "val": 30, "ttl": None},
    {"op": "snapshot", "t": 4}
])
# Returns: [True, True, 10, True, [["a", 10, 2], ["c", 30, 1]]]
```
