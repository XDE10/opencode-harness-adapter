Fix `run_patch(ops)` in `solution.py`.

Implement a deterministic stateful unified-hunk patch applier for lists of exact strings.

State starts with an empty document `lines` and `cursor = 0`. Process `ops` in order and append one result per operation.

Operations:
- `{"op": "load", "lines": [...]}`: replace the document with a copy of `lines` and reset `cursor` to `0`. Append `None`.
- `{"op": "seek", "index": int}`: set `cursor` to `index`. Append `None`. `index` must be an integer (not a bool) with `0 <= index <= len(lines)`; otherwise raise `ValueError`.
- `{"op": "apply", "hunk": [...], "start": int | None}`: apply one hunk. `start` may be omitted or `null`; if present and not `null`, it must be an integer (not a bool), otherwise raise `ValueError`.
  - Each hunk line must be a non-empty string whose first character is one of `" "`, `"-"`, `"+"`. Any other hunk value raises `ValueError`. An empty hunk also raises `ValueError`.
  - The hunk old side is all `" "` and `"-"` line bodies in order. The hunk new side is all `" "` and `"+"` line bodies in order. Context lines (`" "`) must match exactly and are part of both sides.
  - If `start` is an integer, use exactly that index; do not search. If it is omitted or `null`, search from `cursor` through the end of the document and choose the smallest index where the full old side matches. Do not wrap around.
  - If the old side does not match at the chosen index, or the explicit `start` is out of range, append `False` and leave both `lines` and `cursor` unchanged.
  - On success, replace `lines[pos:pos + len(old_side)]` with the new side, set `cursor = pos + len(new_side)`, and append `True`.
- `{"op": "get"}`: append a copy of the current document.
- `{"op": "cursor"}`: append the current integer cursor.
- Any unknown operation raises `ValueError`.

Examples:
`run_patch([{"op": "load", "lines": ["a", "b", "c"]}, {"op": "apply", "hunk": ["-b", "+B"]}, {"op": "get"}])` returns `[None, True, ["a", "B", "c"]]`.

`run_patch([{"op": "load", "lines": ["x", "b", "a"]}, {"op": "apply", "hunk": ["-x", " a", "+X"], "start": 0}, {"op": "get"}])` returns `[None, False, ["x", "b", "a"]]` because the context line expects `"a"` after `"x"`, but the document has `"b"`.
