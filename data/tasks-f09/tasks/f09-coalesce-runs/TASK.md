Fix `coalesce_runs(runs, max_gap=0, min_weight=None)` in `solution.py`.

`runs` is a list of `[start, end, weight]` triples of integers (not `bool`), where
`start <= end` and runs are ordered by non-decreasing `start`.

Iterate through `runs` in order and coalesce consecutive runs whenever
`next_start - cur_end <= max_gap`. Coalescing `[cur_start, cur_end, cur_weight]`
with `[next_start, next_end, next_weight]` produces:
`[cur_start, max(cur_end, next_end), cur_weight + next_weight]`.

If `min_weight` is not `None`, filter the coalesced runs to keep only those with
`weight >= min_weight`.

Validation errors (must raise `ValueError`):
- `max_gap` is not an `int` (or is a `bool`), or `max_gap < 0`.
- `min_weight` is neither `None` nor an `int` (or is a `bool`).
- Any run is not a 3-element list/tuple of ints (`bool` excluded), has `start > end`,
  or has `start < prev_start`.

Example:
```python
coalesce_runs([[1, 4, 2], [4, 7, 3], [10, 12, 1]], max_gap=0, min_weight=2)
# -> [[1, 7, 5]]
```
