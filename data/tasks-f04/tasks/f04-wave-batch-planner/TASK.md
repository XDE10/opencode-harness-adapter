Fix `plan_waves(nodes, edges, batch_limit=None)` in `solution.py`.

Partition `nodes` into sequential execution waves respecting directed
dependencies `[u, v]` (where `u` must execute in an earlier wave than `v`).

Rules & Edge Cases:
- `nodes` is a list of unique string IDs. Duplicate node IDs raise `ValueError`.
- `edges` is a list of `[u, v]` pairs. Unknown endpoints raise `KeyError`.
  Duplicate `[u, v]` edges must be ignored.
- `batch_limit` is `None` (unlimited wave size) or a positive integer (`>= 1`).
  If `batch_limit is not None and batch_limit <= 0`, raise `ValueError`.
- In each wave:
  1. Collect all unscheduled nodes whose prerequisites all finished in earlier
     waves.
  2. Sort these ready candidates lexicographically.
  3. Take at most `batch_limit` candidates (if `batch_limit is not None`) to
     form the current wave.
  4. Only after the wave finishes do its nodes unlock dependents for subsequent
     waves.
- If `nodes` is empty (and `edges` is empty), return `[]`.
- If the graph contains a cycle (including a self-loop), raise `ValueError`.

Example:
```python
plan_waves(["c", "a", "b"], [["a", "b"]], batch_limit=1)
# -> [["a"], ["b"], ["c"]]
```
