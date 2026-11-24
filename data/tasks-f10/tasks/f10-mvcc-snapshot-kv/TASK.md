Fix `run(ops)` in `solution.py` implementing an in-memory MVCC key-value store with Snapshot Isolation and First-Committer-Wins conflict detection.

A monotonic global commit version `ver` starts at `0`. `run(ops)` processes a list of operation dictionaries and returns one value per operation:

- `{"op": "begin", "tx": <str>}`: Start transaction `tx` with snapshot version equal to the current `ver`. Raises `ValueError` if `tx` is already active. Returns the snapshot version (`int`).
- `{"op": "write", "tx": <str>, "key": <str>, "value": <val>}`: Buffer a write of `value` (`value` cannot be `None`, else `ValueError`) for `key` in `tx`. Raises `KeyError` if `tx` is not active. Returns `value`.
- `{"op": "delete", "tx": <str>, "key": <str>}`: Buffer a tombstone deletion for `key` in `tx`. Raises `KeyError` if `tx` is not active, or if `key` is not currently visible to `tx` (either deleted or missing in `tx`'s buffered writes and snapshot). Returns `True`.
- `{"op": "read", "tx": <str>, "key": <str>, "default": <val>}`: Read `key` from `tx`'s own buffered writes first (returning `default`, which defaults to `None`, if tombstoned), or otherwise the latest committed version with `commit_ver <= tx.snap_ver` (returning `default` if absent or tombstoned). Raises `KeyError` if `tx` is not active.
- `{"op": "commit", "tx": <str>}`: Validate First-Committer-Wins: if any key in `tx`'s write set was committed at a version strictly greater than `tx.snap_ver`, abort `tx` (removing it from active transactions) and raise `ValueError`. Otherwise, increment `ver` by `1`, record all buffered writes/tombstones at `ver`, remove `tx` from active transactions, and return the new `ver`. Raises `KeyError` if `tx` is not active.
- `{"op": "abort", "tx": <str>}`: Discard `tx`'s buffered writes and remove `tx` from active transactions. Raises `KeyError` if `tx` is not active. Returns `True`.
- `{"op": "committed_keys", "at_ver": <int>}`: Return a sorted list of keys that exist (non-tombstoned) at `at_ver` (defaults to current `ver` if omitted).
- Unknown `"op"` raises `ValueError`.

Edge cases:
- A transaction that begins *after* another transaction commits (`tx2.snap_ver == tx1.commit_ver`) must be allowed to write and commit the same keys as `tx1`.
- On a write-write conflict during `commit`, `tx` must be aborted and removed from active transactions before raising `ValueError`.
- Falsy values (`0`, `False`, `""`, `[]`) are valid stored values and must not fall back to `default`.

Example:
```python
run([
    {"op": "begin", "tx": "t1"},
    {"op": "write", "tx": "t1", "key": "k", "value": 0},
    {"op": "commit", "tx": "t1"},
    {"op": "begin", "tx": "t2"},
    {"op": "read", "tx": "t2", "key": "k", "default": -1},
])
# -> [0, 0, 1, 1, 0]
```
