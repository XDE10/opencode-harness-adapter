Fix `label_regions(grid, connectivity, min_size)` in `solution.py`.

Implement a deterministic flood-fill labeler for a rectangular character grid.

Inputs:
- `grid`: a non-empty list of non-empty strings of equal length. Each character is either `"."` (open) or `"#"` (blocked).
- `connectivity`: integer `4` or `8`. With `4`, cells are neighbors only up/down/left/right. With `8`, diagonal neighbors also count; diagonal adjacency is direct even if the orthogonal corner cells are blocked.
- `min_size`: non-negative integer. A region is kept iff its open-cell count is at least `min_size`; a region exactly equal to `min_size` is kept.

Return a list of lists of integers with the same shape as `grid`. Blocked cells are always `0`. Scan cells in row-major order. When an unvisited open cell starts a region, flood-fill the whole region. If the region is kept, every cell in it gets the next label, starting at `1`; if it is suppressed, all its cells remain `0` and no label number is consumed. Labels therefore follow the row-major order of each region's first open cell. Do not modify `grid`.

Raise `ValueError` for an empty grid, an empty row, ragged rows, invalid characters, `connectivity` not equal to `4` or `8`, or `min_size` negative. `connectivity` and `min_size` must be real integers; booleans are not accepted.

Examples:
`label_regions(["..", "##"], 4, 0)` returns `[[1, 1], [0, 0]]`.
`label_regions([".#", "#."], 8, 1)` returns `[[1, 0], [0, 1]]`.
