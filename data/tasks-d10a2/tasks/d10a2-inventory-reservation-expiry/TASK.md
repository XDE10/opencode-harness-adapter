Fix `run(ops)` in `solution.py`.

Implement a deterministic inventory reservation state machine. The function receives `ops`, a list of operation dicts, processes them in order, and returns a list of results.

State starts with `stock = 0`, no active reservations, and insertion sequence `0`.

Input rules:
- `ops` must be a list, and each operation must be a dict; otherwise raise `ValueError`.
- Integer fields must be Python `int` values, not `bool`; otherwise raise `ValueError`.
- All required fields must be present; missing or invalid fields raise `ValueError`. Extra keys are ignored.
- `rid` must be a string. `t` may be any integer. `qty` and `ttl` must be positive integers. `stock` must be a nonnegative integer.
- Unknown operation names raise `ValueError`.

Operations:
1. `{"op": "init", "stock": int}` sets `stock`, clears all reservations, resets insertion sequence to `0`, and appends `None`.
2. `{"op": "reserve", "rid": str, "qty": int, "t": int, "ttl": int}` first removes every active reservation with `expires_at <= t`. If `rid` is still active, append `False` and leave it unchanged. Otherwise, if `qty <= stock - sum(active reservation quantities)`, create a reservation with `expires_at = t + ttl` and the next insertion sequence, increment the sequence, and append `True`; otherwise append `False`. A failed reserve still performs expiration first.
3. `{"op": "release", "rid": str, "t": int}` first removes every active reservation with `expires_at <= t`, then removes `rid` if active and appends `True`; otherwise appends `False`.
4. `{"op": "commit", "rid": str, "t": int}` first removes every active reservation with `expires_at <= t`. If `rid` is active, reduce `stock` by that reservation's `qty`, remove it, and append `True`; otherwise append `False`.
5. `{"op": "snapshot", "t": int}` first removes every active reservation with `expires_at <= t`, then appends a list of rows `[rid, qty, expires_at]` ordered by `(expires_at, insertion_sequence)` ascending. Insertion sequence increases only on successful `reserve` and resets on `init`.

Examples:
`run([{"op": "init", "stock": 2}, {"op": "reserve", "rid": "a", "qty": 2, "t": 0, "ttl": 1}, {"op": "reserve", "rid": "b", "qty": 2, "t": 1, "ttl": 3}])` returns `[None, True, True]`.

`run([{"op": "init", "stock": 3}, {"op": "reserve", "rid": "z", "qty": 1, "t": 0, "ttl": 5}, {"op": "reserve", "rid": "a", "qty": 2, "t": 0, "ttl": 2}, {"op": "snapshot", "t": 1}])` returns `[None, True, True, [["a", 2, 2], ["z", 1, 5]]]`.
