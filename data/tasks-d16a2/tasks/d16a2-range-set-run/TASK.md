Fix `run(ops)` in `solution.py`.

Implement a deterministic set of disjoint inclusive integer intervals. The set is initially empty. Each operation is a dict and is processed in order.

Operation forms:
- `{"op": "add", "l": int, "r": int}`: add every integer in `[l, r]` to the set, then append `None`.
- `{"op": "remove", "l": int, "r": int}`: remove every integer in `[l, r]` from the set, then append `None`.
- `{"op": "query", "l": int, "r": int}`: append the sorted list of intersections between the current set and `[l, r]`, clipped to `[l, r]`. Each intersection is a two-element list `[start, end]`. If there is no intersection, append `[]`.

Rules:
- Intervals are inclusive on both ends.
- The stored representation must always be sorted, disjoint, and non-adjacent. Adjacent integer intervals such as `[1, 3]` and `[4, 6]` are merged into `[1, 6]`.
- `remove` may split one stored interval into two intervals.
- Extra keys in an operation dict are ignored.
- If `ops` is not a list, an element of `ops` is not a dict, `op` is missing or not one of the three names, either bound is missing, a bound is not a Python `int` (bool is not accepted), or `l > r`, raise `ValueError`.

Examples:
`run([{"op": "add", "l": 10, "r": 12}, {"op": "add", "l": 13, "r": 15}, {"op": "query", "l": 11, "r": 14}])` returns `[None, None, [[11, 14]]]`.
`run([{"op": "add", "l": 0, "r": 9}, {"op": "remove", "l": 3, "r": 5}, {"op": "query", "l": 0, "r": 20}])` returns `[None, None, [[0, 2], [6, 9]]]`.
