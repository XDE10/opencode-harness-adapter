Fix `run(ops)` in `solution.py`.

Implement a deterministic set of inclusive integer intervals. The set is initially empty for every call to `run(ops)` and does not persist between calls. Integers may be negative.

Operations are processed in order. Each operation is a dict with an `"op"` key:

- `{"op": "add", "lo": int, "hi": int}`: add every integer in `[lo, hi]`. Overlapping or adjacent ranges are coalesced. Append `None`.
- `{"op": "remove", "lo": int, "hi": int}`: remove every integer in `[lo, hi]`. This may split an existing interval. Append `None`.
- `{"op": "query", "lo": int, "hi": int}`: append the intersection of the current set with `[lo, hi]` as a list of `[start, end]` pairs, sorted by `start`. Returned intervals are canonical: non-overlapping and non-adjacent (`next_start > previous_end + 1`). Append `[]` if there is no overlap.
- `{"op": "contains", "x": int}`: append `True` iff `x` is currently in the set, otherwise `False`.
- `{"op": "reset"}`: clear all stored intervals. Append `None`.

For `add`, `remove`, and `query`, `lo <= hi` is required; otherwise raise `ValueError` when that operation is reached. An unknown `"op"` value raises `ValueError`. Missing required keys raise `KeyError`. The result list contains one entry per processed operation; if an exception is raised, processing stops and the exception propagates.

Examples:
`run([{"op": "add", "lo": 1, "hi": 2}, {"op": "add", "lo": 3, "hi": 5}, {"op": "query", "lo": 0, "hi": 9}])` returns `[None, None, [[1, 5]]]`.

`run([{"op": "add", "lo": 1, "hi": 10}, {"op": "remove", "lo": 4, "hi": 6}, {"op": "contains", "x": 5}, {"op": "query", "lo": 0, "hi": 12}])` returns `[None, None, False, [[1, 3], [7, 10]]]`.
