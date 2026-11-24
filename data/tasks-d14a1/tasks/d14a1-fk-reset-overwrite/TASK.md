Fix `run(ops)` in `solution.py`.

Implement a deterministic table primary-key/foreign-key violation checker driven by stateful operations. Each call to `run(ops)` starts from empty state. `ops` is a list of operation dictionaries; all ids are integers, and `pid` is either an integer or `None`. `pid = 0` is a normal parent id; only `None` means “no parent reference”.

State:
- Parent table: a set of currently present parent ids.
- Child table: a mapping from child id to `pid`.
- A child is a violation iff `pid is not None` and `pid` is not currently present in the parent table.

Operations:
1. `{"op": "add_parent", "id": int}` inserts a parent id. If that parent id is already present, raise `ValueError`.
2. `{"op": "del_parent", "id": int}` removes the parent id if present; otherwise it is a no-op. Children referencing it are not deleted and may become violations.
3. `{"op": "upsert_child", "id": int, "pid": int | None}` inserts or overwrites the child id. If the child already existed, its previous foreign-key reference must be replaced and must no longer count. A child whose `pid` is missing from the parent table is allowed and is reported as a violation.
4. `{"op": "del_child", "id": int}` removes the child if present; otherwise it is a no-op. Its foreign-key reference is removed.
5. `{"op": "reset"}` clears all parents, children, and foreign-key references.
6. `{"op": "report"}` appends one snapshot to the returned list. A snapshot is a dict with exactly these keys:
   - `"parents"`: sorted list of current parent ids.
   - `"children"`: sorted list of current child ids.
   - `"bad_children"`: sorted list of current violating child ids.

Any unknown operation raises `ValueError`. The function returns the list of report snapshots in encounter order.

Examples:
`run([{"op": "add_parent", "id": 1}, {"op": "upsert_child", "id": 10, "pid": 1}, {"op": "del_parent", "id": 1}, {"op": "report"}])` returns `[{"parents": [], "children": [10], "bad_children": [10]}]`.

`run([{"op": "upsert_child", "id": 4, "pid": 9}, {"op": "reset"}, {"op": "report"}])` returns `[{"parents": [], "children": [], "bad_children": []}]`.
