Fix `run_tx_kv(ops)` in `solution.py`.

Implement a transactional key-value store supporting nested transactions (`begin`, `commit`, `rollback`) and an exact-value secondary index (`count`). Keys are strings (`str`) and values are integers (`int`, including `0` and negative integers).

`run_tx_kv(ops)` processes a list of operation dictionaries in order and returns a list of outputs (one entry per operation):

1. `{"op": "set", "key": str, "val": int}`:
   Set `key` to `val` in the current state. Append `None` to outputs.
2. `{"op": "delete", "key": str}`:
   If `key` is currently present, remove it and append `True`; otherwise append `False`.
3. `{"op": "get", "key": str}`:
   Append the current integer value for `key` if present, or `None` if absent.
4. `{"op": "count", "val": int}`:
   Append the number of currently present keys mapped to `val` (`int`).
5. `{"op": "begin"}`:
   Open a new nested transaction scope and append the current active transaction depth (`int >= 1`, e.g. `1` for the outermost transaction).
6. `{"op": "commit"}`:
   Merge all changes from the innermost open transaction into its parent scope (or the root state if depth was `1`) and close that transaction. Append the remaining active transaction depth (`int >= 0`). If no transaction is open (`depth == 0`), raise `ValueError`.
7. `{"op": "rollback"}`:
   Revert all `set` and `delete` operations performed since the matching innermost `begin`, close that transaction, and append the remaining active transaction depth (`int >= 0`). Everything (both key lookups and `count` queries) must reflect the state right before that `begin`. If no transaction is open (`depth == 0`), raise `ValueError`.
8. Any unknown `"op"` string must raise `ValueError`.

Example:
```python
run_tx_kv([
    {"op": "set", "key": "a", "val": 0},
    {"op": "begin"},
    {"op": "set", "key": "a", "val": 5},
    {"op": "rollback"},
    {"op": "get", "key": "a"},
    {"op": "count", "val": 0},
])
# Returns: [None, 1, None, 0, 0, 1]
```
