Fix `run(ops)` in `solution.py`.

The grader calls `run(ops)` with one positional argument: `ops`, a list of operation dictionaries. Return a list with one result dictionary per processed operation. If `ops` is empty, return `[]`.

Coordinate convention: coordinates are zero-based `[row, col]` pairs. A grid with `rows` rows and `cols` cols has valid rows `0..rows-1` and valid cols `0..cols-1`. Directions are `N` (row - 1), `E` (col + 1), `S` (row + 1), `W` (col - 1).

Each result dictionary must have exactly these keys:
- `"pos"`: current `[row, col]`
- `"heading"`: one of `"N"`, `"E"`, `"S"`, `"W"`
- `"blocked"`: boolean
- `"visited"`: sorted list of unique visited coordinates, row-major (sort by row, then col)

Operations:
1. `{"op": "init", "rows": int, "cols": int, "obstacles": [[r, c], ...], "start": [r, c], "heading": str}`
   - Starts a fresh simulation and discards any previous state.
   - `rows` and `cols` must be positive strict integers.
   - `heading` must be one of `"N"`, `"E"`, `"S"`, `"W"`.
   - `obstacles` must be a list of in-bounds coordinate pairs; duplicates are harmless.
   - `start` must be an in-bounds coordinate pair not in `obstacles`.
   - The robot starts at `start`, and `visited` is exactly `[start]`.
   - Appends a result with `"blocked": false`.
2. `{"op": "move", "steps": int}`
   - `steps` must be a strict integer `>= 0`.
   - The robot attempts to move one cell at a time in its current heading.
   - Before each step, if the next cell is outside the grid or is an obstacle, the robot stops before entering it, sets `"blocked": true`, and ignores the remaining steps.
   - Every entered cell is added to `visited`; revisiting a cell does not duplicate it.
   - If `steps == 0`, no movement occurs and `"blocked": false`.
3. `{"op": "turn", "dir": str}`
   - `dir` must be `"left"` or `"right"`.
   - Left rotation maps `N -> W -> S -> E -> N`.
   - Right rotation maps `N -> E -> S -> W -> N`.
   - Turning does not move or add to `visited`; result has `"blocked": false`.
4. `{"op": "reset"}`
   - Returns the robot to the most recent `init` start and heading.
   - Clears `visited` to exactly `[start]`.
   - Result has `"blocked": false`.

All integer fields are strict Python `int`s; `bool` is not accepted. Raise `ValueError` for invalid fields, invalid operation dictionaries, unknown operations, any non-`init` operation before an `init`, `ops` not being a list, or an operation not being a dictionary.

Examples:
`run([{"op": "init", "rows": 2, "cols": 3, "obstacles": [], "start": [0, 1], "heading": "E"}, {"op": "move", "steps": 1}])` returns:
`[{"pos": [0, 1], "heading": "E", "blocked": false, "visited": [[0, 1]]}, {"pos": [0, 2], "heading": "E", "blocked": false, "visited": [[0, 1], [0, 2]]}]`

`run([{"op": "init", "rows": 2, "cols": 2, "obstacles": [], "start": [0, 0], "heading": "N"}, {"op": "turn", "dir": "right"}, {"op": "move", "steps": 2}])` returns:
`[{"pos": [0, 0], "heading": "N", "blocked": false, "visited": [[0, 0]]}, {"pos": [0, 0], "heading": "E", "blocked": false, "visited": [[0, 0]]}, {"pos": [0, 1], "heading": "E", "blocked": true, "visited": [[0, 0], [0, 1]]}]`
