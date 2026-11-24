Fix `run(ops)` in `solution.py`.

Implement a deterministic stable multi-key group-by rollup over a list of operation dicts. `run(ops)` returns a Python list with exactly one result per operation.

State is an ordered mapping keyed by the tuple of strings in a group's `keys` list. New groups are appended to the order. Existing groups keep their original position. A `reset` removes only the named group; if it was absent, nothing happens. Removing and later re-adding a group puts it at the end. `clear` removes all groups.

Operations:
- `{"op": "add", "keys": [str, ...], "value": int}`: update that group's rollup and append `None`.
- `{"op": "get", "keys": [str, ...]}`: append a copy of that group's rollup, or `None` if absent.
- `{"op": "emit"}`: append a list of copies of all current rollups in first-seen order. This does not clear state.
- `{"op": "reset", "keys": [str, ...]}`: remove exactly that group and append `None`.
- `{"op": "clear"}`: remove all groups and append `None`.

A rollup dict has exactly these fields: `keys` (the original key list), `count`, `sum`, `min`, `max`, and `last` (most recent value). `min` and `max` include zero and negative values normally. Return ordinary lists and dicts, not tuples.

`keys` must be a non-empty list of strings. `value` must be an `int`, and `bool` is not accepted. Invalid `ops`, invalid operation dicts, missing required fields, invalid keys/values, or unknown operation names must raise `ValueError`.

Example:
`run([{"op":"add","keys":["team","a"],"value":4},{"op":"add","keys":["team","a"],"value":1},{"op":"get","keys":["team","a"]},{"op":"emit"}])` returns `[None, None, {"keys":["team","a"],"count":2,"sum":5,"min":1,"max":4,"last":1}, [{"keys":["team","a"],"count":2,"sum":5,"min":1,"max":4,"last":1}]]`.

Example:
`run([{"op":"add","keys":["x"],"value":2},{"op":"add","keys":["y"],"value":3},{"op":"reset","keys":["x"]},{"op":"emit"}])` returns `[None, None, None, [{"keys":["y"],"count":1,"sum":3,"min":3,"max":3,"last":3}]]`.
