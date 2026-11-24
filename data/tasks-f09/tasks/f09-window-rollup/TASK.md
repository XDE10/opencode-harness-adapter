Fix `windowed_rollup(seq, size, step=1, agg="sum", pad=None, partial=False)` in `solution.py`.

Slide a window of target length `size` over `seq` (a list of integers, `bool`
excluded), advancing the window start index `i` by `step` from `0` while `i < len(seq)`.

For each candidate slice `w = seq[i : i + size]`:
- If `len(w) == size`, compute the aggregate of `w`.
- If `len(w) < size` and `pad is not None`, right-pad `w` with `pad` to length
  `size` and compute the aggregate.
- If `len(w) < size` and `pad is None`, include the unpadded slice `w` only when
  `partial` is `True`; otherwise omit it.

If `seq` is empty, return `[]`.

Supported `agg` functions (all return `int`):
- `"sum"`: sum of elements in the window.
- `"min"`: minimum element in the window.
- `"max"`: maximum element in the window.
- `"first"`: first element of the window.
- `"last"`: last element of the window.
- `"span"`: `max(w) - min(w)`.

Validation errors (must raise `ValueError`):
- `size` or `step` is not an `int` (or is a `bool`), or `< 1`.
- `pad` is neither `None` nor an `int` (or is a `bool`).
- Any element of `seq` is not an `int` (or is a `bool`).
- `agg` is not one of the supported names above.

Example:
```python
windowed_rollup([1, 2, 3, 4], size=3, step=2, agg="sum", pad=0)
# -> [6, 7]
```
