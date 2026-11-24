Fix `run(ops)` in `solution.py`.

Implement a deterministic weighted union-find constraint tracker. The function receives a list of operation dicts and returns a list of JSON-serializable results, one per operation. State starts empty for each call to `run`.

Names are strings. Constraints have the form `value[y] - value[x] == d`, where `d` is an integer and may be negative or zero. Absolute values are never exposed; only differences between connected names are determined.

Operations:
- `{"op": "add", "x": str, "y": str, "d": int}`: If `x` or `y` is unknown, create it as an isolated name. If `x` and `y` are not connected, add the constraint and append `{"ok": true}`. If they are already connected, append `{"ok": true}` only when the current `value[y] - value[x]` equals `d`; otherwise append `{"ok": false}` and leave state unchanged. For `x == y`, the current difference is `0`, so only `d == 0` is consistent.
- `{"op": "diff", "x": str, "y": str}`: If either name is unknown, create it as isolated. If connected, append `{"connected": true, "diff": value[y] - value[x]}`; otherwise append `{"connected": false, "diff": null}`.
- `{"op": "components"}`: Append the current connected components. Each component is a list of names sorted lexicographically. The component list is sorted by the first name of each component. Isolated known names appear as singleton components.
- `{"op": "reset"}`: Clear all names and constraints, then append `{"ok": true}`.

Extra fields in operation dicts are ignored. Raise `ValueError` immediately if an operation is not a dict, if `op` is missing or unknown, if `x` or `y` is not a string where required, or if `d` is missing/not an integer where required. `bool` is not accepted as an integer `d`.

Examples:
`run([{"op": "add", "x": "a", "y": "b", "d": 2}, {"op": "diff", "x": "a", "y": "b"}])` returns `[{"ok": true}, {"connected": true, "diff": 2}]`.

`run([{"op": "diff", "x": "a", "y": "a"}, {"op": "reset"}, {"op": "components"}])` returns `[{"connected": true, "diff": 0}, {"ok": true}, []]`.
