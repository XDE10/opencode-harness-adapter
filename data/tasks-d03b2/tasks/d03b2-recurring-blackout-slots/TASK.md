Fix `build_schedule(series_list, blackouts, horizon)` in `solution.py`.

You are building an interval-clipping and conflict-detection engine for recurring booking series over half-open integer time intervals `[start, end)`.

### Parameters
- `series_list`: list of booking series dicts, each containing:
  - `"name"` (`str`): unique series identifier.
  - `"start"` (`int`): start time of the first occurrence (`>= 0`).
  - `"duration"` (`int`): duration of each occurrence (`> 0`).
  - `"step"` (`int`): recurrence period (`> 0`). Occurrence `k` (`k = 0, 1, 2, ...`) spans `[start + k * step, start + k * step + duration)`.
  - `"count"` (`int`): number of occurrences generated (`>= 1`).
  - `"min_chunk"` (`int`): minimum acceptable duration (`>= 1`) for any remaining fragment after horizon clipping and blackout subtraction.
- `blackouts`: list of `[b_start, b_end]` pairs representing half-open blackout windows `[b_start, b_end)`.
- `horizon`: a two-element list `[h_start, h_end]` representing the half-open scheduling window `[h_start, h_end)`.

### Validation
Raise `ValueError` before processing if:
- `horizon` does not satisfy `0 <= h_start < h_end`.
- Any blackout `[b_start, b_end]` has `b_start < 0` or `b_end <= b_start`.
- Any series has `start < 0`, `duration <= 0`, `step <= 0`, `count < 1`, or `min_chunk < 1`.
- Duplicate `"name"` values exist in `series_list`.

### Clipping & Blackout Subtraction Rules
1. **Horizon Clipping**: For every generated occurrence `[s, e)` of a series, intersect it with `[h_start, h_end)` to obtain `[max(s, h_start), min(e, h_end))`. If the intersection is empty (`start >= end`), discard it.
2. **Blackout Subtraction**: Subtract all blackout intervals `[b_start, b_end)` from each horizon-clipped occurrence. If a blackout lies strictly inside an occurrence (`s < b_start` and `b_end < e`), it splits that occurrence into two fragments `[s, b_start)` and `[b_end, e)`. Multiple blackouts may overlap, touch, or split an occurrence into several disjoint fragments.
3. **Minimum Chunk Filtering**: After all blackouts have been subtracted from an occurrence, keep only fragments `[f_start, f_end)` whose length satisfies `f_end - f_start >= min_chunk`.
4. **Intra-Series Merging**: If a series has overlapping or adjacent kept fragments (for example, when `step <= duration`), merge any overlapping or touching (`f1_end >= f2_start`) kept fragments belonging to the **same** series into a single contiguous interval `[start, end)`.

### Return Value
Return a dict with two keys:
- `"slots"`: list of `[start, end, name]` for all final merged intervals across all series, sorted by `(start, end, name)` ascending.
- `"conflicts"`: list of `[c_start, c_end, [name_1, name_2, ...]]` representing all non-empty time intervals (`c_start < c_end`) where **2 or more** distinct series are active simultaneously:
  - Partition the timeline at all slot start and end coordinates into elementary half-open segments `[t_i, t_{i+1})`.
  - For each elementary segment covered by at least 2 series, collect the sorted list of active series names.
  - Merge adjacent elementary segments `[t_1, t_2)` and `[t_2, t_3)` if and only if they have the **exact same** list of active series names.

### Example
```python
build_schedule(
    series_list=[
        {"name": "alpha", "start": 0, "duration": 20, "step": 30, "count": 1, "min_chunk": 5},
        {"name": "beta", "start": 5, "duration": 15, "step": 30, "count": 1, "min_chunk": 5},
    ],
    blackouts=[[8, 12]],
    horizon=[0, 25],
)
# Returns:
# {
#   "slots": [
#     [0, 8, "alpha"],
#     [5, 8, "beta"],
#     [12, 20, "alpha"],
#     [12, 20, "beta"]
#   ],
#   "conflicts": [
#     [5, 8, ["alpha", "beta"]],
#     [12, 20, ["alpha", "beta"]]
#   ]
# }
```
