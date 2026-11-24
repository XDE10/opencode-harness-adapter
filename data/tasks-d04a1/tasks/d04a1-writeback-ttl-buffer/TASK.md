Fix `run(max_dirty, ops)` in `solution.py`.

Implement a deterministic write-back cache buffer sitting in front of a persistent backing store, supporting TTL expiration, dirty-entry flushing, and rollback of uncommitted writes.

### State & Rules
- `max_dirty`: positive integer (`>= 1`). Raise `ValueError` if `max_dirty < 1`.
- The system maintains:
  - `store`: persistent dict (`key -> int`) of committed values. Initially empty.
  - `buffer`: in-memory cache of dirty or clean cached entries. Each buffered entry tracks `val` (`int`), `dirty` (`bool`), `updated_at` (`int`, timestamp of the last `write` or `read`-load into buffer), and `expire_at` (`int | None`).
- **Expiration purge (runs first on every operation at timestamp `t`)**:
  - Before executing any operation at timestamp `t`, remove all entries in `buffer` where `expire_at is not None and expire_at <= t`.
  - Expired entries in `buffer` are **discarded without flushing** to `store` (even if they were `dirty`). `store` itself never expires.

### Operations (`ops`)
Timestamps `t` are non-decreasing integers. Each operation appends one result to the returned list:

1. `{"op": "write", "t": int, "key": str, "val": int, "ttl": int | None}`:
   - First purge expired buffer entries at `t`.
   - If `ttl is not None and ttl <= 0`, raise `ValueError`.
   - If `key` is not already a dirty entry in `buffer`, and the number of currently dirty entries in `buffer` equals `max_dirty`:
     - Flush the **single** dirty entry in `buffer` with the smallest `updated_at` timestamp (breaking ties by lexicographically smallest `key`): write its `val` to `store[victim_key]` and mark that entry `dirty = False` (it remains in `buffer` with its existing `val`, `updated_at`, and `expire_at`).
   - Insert or update `key` in `buffer` with `val = val`, `dirty = True`, `updated_at = t`, and `expire_at = None if ttl is None else t + ttl`.
   - Append `None`.

2. `{"op": "read", "t": int, "key": str}`:
   - First purge expired buffer entries at `t`.
   - If `key` is in `buffer`, append its buffered `val` (do **not** change `updated_at` or `expire_at`).
   - Otherwise, if `key` is in `store`, load it into `buffer` as a clean entry (`val = store[key]`, `dirty = False`, `updated_at = t`, `expire_at = None`) and append `store[key]`.
   - Otherwise, append `None`.

3. `{"op": "flush", "t": int}`:
   - First purge expired buffer entries at `t`.
   - For every currently dirty entry in `buffer`, copy its `val` into `store[key]` and set `dirty = False` (leaving the entry in `buffer`).
   - Append the count (`int`) of entries that were flushed during this call.

4. `{"op": "rollback", "t": int}`:
   - First purge expired buffer entries at `t`.
   - Discard (delete from `buffer`) all entries in `buffer` that currently have `dirty == True`. Clean entries in `buffer` and committed values in `store` are untouched.
   - Append the count (`int`) of dirty entries discarded.

5. `{"op": "status", "t": int}`:
   - First purge expired buffer entries at `t`.
   - Append `{"dirty": dirty_keys, "store": sorted_store}` where:
     - `dirty_keys` is a sorted list of keys in `buffer` with `dirty == True`.
     - `sorted_store` is a list of `[key, val]` pairs from `store` sorted by `key` ascending.

If an operation dict has an unknown `"op"`, raise `ValueError`.

### Example
```python
run(2, [
    {"op": "write", "t": 1, "key": "a", "val": 10, "ttl": 5},
    {"op": "write", "t": 2, "key": "b", "val": 20, "ttl": None},
    {"op": "flush", "t": 6},
    {"op": "status", "t": 6}
])
# At t=6, "a" expired (1+5 <= 6) before flush, so only "b" is flushed.
# Returns: [None, None, 1, {"dirty": [], "store": [["b", 20]]}]
```
