Fix `run(ops)` in `solution.py`.

Implement a deterministic stateful directed weighted graph driver. `ops` is a list of operation dictionaries processed in order. The graph starts empty. Node labels are strings; weights are positive integers (booleans are not accepted). The function returns a list with one entry per operation.

Operations:
- `{"op": "add", "u": ..., "v": ..., "w": ...}`: add or replace the directed edge `u -> v` with weight `w`. Adding introduces both endpoints as nodes. Append `None`.
- `{"op": "remove", "u": ..., "v": ...}`: remove edge `u -> v` if present; do not remove nodes. Append `None`.
- `{"op": "reset"}`: clear all edges and all nodes. Append `None`.
- `{"op": "path", "s": ..., "t": ...}`: compute a shortest path from `s` to `t`. Path queries do not mutate the graph. If either endpoint is not currently a node, append `None`. If `s == t` and the node exists, append `{"dist": 0, "path": [s]}`. If unreachable, append `None`. Otherwise append `{"dist": total_weight, "path": [node, ...]}`.

When several paths have the same total weight, choose the one with fewest edges; if still tied, choose the lexicographically smallest path sequence. Lexicographic comparison is over the list of node strings.

Raise `ValueError` immediately for an unknown op or for a non-positive/non-int weight.

Examples:
`run([{"op": "add", "u": "a", "v": "b", "w": 2}, {"op": "path", "s": "a", "t": "b"}])` returns `[None, {"dist": 2, "path": ["a", "b"]}]`.

`run([{"op": "add", "u": "s", "v": "t", "w": 2}, {"op": "add", "u": "s", "v": "a", "w": 1}, {"op": "add", "u": "a", "v": "t", "w": 1}, {"op": "path", "s": "s", "t": "t"}])` returns `[None, None, None, {"dist": 2, "path": ["s", "t"]}]` because the direct path has fewer edges.
