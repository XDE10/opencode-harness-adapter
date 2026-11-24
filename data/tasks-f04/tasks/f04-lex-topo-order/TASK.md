Fix `topo_order(nodes, edges, reverse=False)` in `solution.py`.

Return a topological ordering of `nodes` respecting all directed dependency
edges `[u, v]` (meaning `u` must appear before `v`).

Rules & Edge Cases:
- `nodes` is a list of unique string node IDs. If `nodes` contains duplicates,
  raise `ValueError`.
- `edges` is a list of `[u, v]` pairs. If either `u` or `v` is not in `nodes`,
  raise `KeyError`. Duplicate `[u, v]` edges must be ignored (not double-counted).
- At each step, among all remaining nodes whose prerequisites have all been
  placed, select the lexicographically smallest node when `reverse=False`, or
  the lexicographically largest node when `reverse=True`.
- If `nodes` is empty (and `edges` is empty), return `[]`.
- If the graph contains any cycle (including a self-loop `[u, u]`), raise
  `ValueError`.

Example:
```python
topo_order(["a", "b", "c"], [["a", "b"]])
# -> ["a", "b", "c"]
topo_order(["a", "b", "c", "d"], [["d", "b"]], reverse=True)
# -> ["d", "c", "b", "a"]
```
