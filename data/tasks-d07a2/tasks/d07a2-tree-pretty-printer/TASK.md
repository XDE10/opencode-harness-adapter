Fix `render_tree(nodes)` in `solution.py`.

Implement a deterministic tree pretty-printer for a forest of nodes.

- `nodes` must be a `list`. Each node must be a `dict` with exactly the keys `"id"`, `"label"`, and `"children"`.
- `id` must be an `int` (but not `bool`); `label` must be a `str`; `children` must be a `list` of nodes with the same rules. `label` may be empty and `id` may be negative.
- All ids in the entire forest must be unique.
- If any of these structure rules is violated, raise `ValueError`. An empty `nodes` list returns `[]`.
- Do not mutate the input.

Rendering:
- The text shown for a node is exactly `label + "#" + str(id)`.
- Roots are treated as siblings and sorted by `(label, id)` ascending. Children of every node are sorted the same way.
- Each root is printed with no prefix and no connector, followed by its children.
- A child line is `prefix + "├── " + text` for every non-last sibling and `prefix + "└── " + text` for the last sibling.
- Descendants of a non-last child use `prefix + "│   "`; descendants of a last child use `prefix + "    "`.

Examples:
`render_tree([{"id": 2, "label": "b", "children": []}, {"id": 1, "label": "a", "children": []}])` returns `["a#1", "b#2"]`.

`render_tree([{"id": 1, "label": "r", "children": [{"id": 3, "label": "b", "children": []}, {"id": 2, "label": "a", "children": [{"id": 4, "label": "leaf", "children": []}]}]}])` returns:
`["r#1", "├── a#2", "│   └── leaf#4", "└── b#3"]`.
