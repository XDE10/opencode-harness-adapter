Fix `sorted_merge_join(left, right, how="inner")` in `solution.py`.

`left` and `right` are sequences of `[key, value]` two-element pairs sorted in
non-decreasing integer `key` order (`key` must be an `int`, not a `bool`). Duplicate
keys are allowed in both inputs.

Perform a sorted merge join according to `how`:
- `"inner"`: emit `[key, left_val, right_val]` only for keys present in both sides.
- `"left"`: emit all `"inner"` matches plus `[key, left_val, None]` for unmatched `left` items.
- `"right"`: emit all `"inner"` matches plus `[key, None, right_val]` for unmatched `right` items.
- `"outer"`: emit all `"inner"` matches plus unmatched items from both sides.

Ordering & tie-breaking:
- Output is ordered by `key` ascending.
- When a `key` appears `m` times in `left` and `n` times in `right`, emit all
  `m * n` combinations in row-major `(left_item, right_item)` order.

Validation errors (must raise `ValueError`):
- `how` is not one of `"inner"`, `"left"`, `"right"`, `"outer"`.
- Any item is not a 2-element list/tuple or has a non-integer (`bool` included) key.
- Either `left` or `right` has `curr_key < prev_key`.

Example:
```python
sorted_merge_join([[1, "a"], [2, "b"]], [[2, 10], [3, 20]], how="left")
# -> [[1, "a", None], [2, "b", 10]]
```
