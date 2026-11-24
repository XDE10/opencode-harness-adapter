Fix `run(ops)` in `solution.py` implementing an in-memory transactional key-value store with SQL-style savepoints.

`ops` is a list of operation dictionaries executed sequentially. `run(ops)` returns one result per operation:

- `{"op": "begin"}`: Start a transaction. Raises `ValueError` if a transaction is already active. Returns `True`.
- `{"op": "savepoint", "name": <str>}`: Push a named savepoint capturing the current transactional state. Raises `ValueError` if no transaction is active. Returns the total number of active savepoints (`int`).
- `{"op": "rollback_to", "name": <str>}`: Restore the transactional store state to the most recent savepoint named `name`, discarding any savepoints created *after* it while keeping `name` itself active so further rollbacks to `name` remain possible. Raises `ValueError` if no transaction is active, or `KeyError` if `name` does not exist. Returns the remaining savepoint count (`int`).
- `{"op": "release", "name": <str>}`: Remove the most recent savepoint named `name` and all savepoints created after it without reverting store changes. Raises `ValueError` if no transaction is active, or `KeyError` if `name` does not exist. Returns the remaining savepoint count (`int`).
- `{"op": "commit"}`: Commit the active transaction and clear all savepoints. Raises `ValueError` if no transaction is active. Returns the number of keys in the committed store.
- `{"op": "rollback"}`: Abort the active transaction, restore pre-`begin` state, and clear all savepoints. Raises `ValueError` if no transaction is active. Returns the number of keys in the store.
- `{"op": "set", "key": <str>, "value": <val>}`: Set `key` to `value` (must not be `None`, else raises `ValueError`). Values may be ints, strings, bools, or lists. Returns `value`.
- `{"op": "delete", "key": <str>}`: Delete `key`; raises `KeyError` if `key` is missing. Returns `True`.
- `{"op": "get", "key": <str>, "default": <val>}`: Return value for `key`, or `default` (`None` if omitted) if missing.
- `{"op": "snapshot"}`: Return a shallow-copied dict of the current visible key-value pairs with keys in sorted order.
- Unknown `"op"` raises `ValueError`.

Edge cases:
- Subsequent writes after `rollback_to` must not mutate the saved snapshot of that savepoint (mutating or setting keys and rolling back to the same savepoint a second time must restore the original savepoint state).
- Falsy values (`0`, `False`, `""`, `[]`) are valid stored values and must not trigger `default`.

Example:
```python
run([
    {"op": "begin"},
    {"op": "set", "key": "x", "value": 1},
    {"op": "savepoint", "name": "sp1"},
    {"op": "set", "key": "x", "value": 2},
    {"op": "rollback_to", "name": "sp1"},
    {"op": "get", "key": "x"},
    {"op": "commit"},
])
# -> [True, 1, 1, 2, 1, 1, 1]
```
