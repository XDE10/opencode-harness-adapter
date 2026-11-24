Fix `build_sequence(jobs, deps)` in `solution.py`.

Schedule jobs in a single valid topological execution sequence using a
deterministic priority rule.

Rules & Edge Cases:
- `jobs` is a list of dicts, each with keys `"name"` (str), `"priority"` (int),
  and `"duration"` (int).
- Duplicate job names must raise `ValueError`.
- Negative `"duration"` (`duration < 0`) must raise `ValueError`; `duration == 0`
  is valid. `"priority"` may be negative, zero, or positive.
- `deps` is a list of `[prereq, dependent]` pairs (`prereq` must complete before
  `dependent`). If either job name is not in `jobs`, raise `KeyError`. Duplicate
  `[prereq, dependent]` pairs must be ignored.
- At each step, among all remaining jobs whose prerequisites have all been
  scheduled, select the next job by:
  1. Highest `"priority"` first
  2. Shortest `"duration"` first
  3. Lexicographically smallest `"name"` first
- If `jobs` is empty (and `deps` is empty), return `[]`.
- If a dependency cycle exists (including a self-loop), raise `ValueError`.

Example:
```python
jobs = [
    {"name": "lint", "priority": 2, "duration": 3},
    {"name": "test", "priority": 2, "duration": 1},
    {"name": "deploy", "priority": 5, "duration": 2},
]
build_sequence(jobs, [["test", "deploy"]])
# -> ["test", "deploy", "lint"]
```
