Fix `run_query_session(ops)` in `solution.py`.

Implement a stateful URL query-parameter session processor supporting nested bracket keys (`a[b][]=v`) and one-level shell-style brace expansion (`{x,y}`) in both keys and values.

### Brace Expansion Rules
Before parsing `key=value` pairs or key paths, a helper expands top-level `{...}` groups:
- A brace group `{alt1,alt2,...}` with **at least one unescaped comma** expands the string into multiple strings in left-to-right Cartesian order (e.g., `env[{dev,prod}][{a,b}]` expands to `env[dev][a]`, `env[dev][b]`, `env[prod][a]`, `env[prod][b]`).
- A brace pair with **no unescaped comma** (e.g. `{id}` or `{}`) is NOT expanded; its `{` and `}` characters are kept literally.
- Any character preceded by `'\'` (including `\,`, `\{`, `\}`, `\\`) is escaped and treated as a literal character (with the escaping backslash removed in the final expanded string).
- Nested `{` inside an open `{...}` or an unclosed `{` or unmatched `}` (when not escaped by `'\'`) must raise `ValueError`.

### Query Assignment & Path Semantics
The session maintains a nested dictionary `state` (initially `{}`).
- `{"op": "ingest", "query": str}`:
  - If `query` is `""`, do nothing and append the number of applied assignments (`0`).
  - Split `query` on `'&'` (ignoring empty segments caused by leading/trailing/repeated `'&'`).
  - Each segment is split on the **first** `'='` into `raw_key` and `raw_val` (if `'='` is absent, `raw_val` is `""`).
  - Expand `raw_key` into `keys` and `raw_val` into `vals` using brace expansion. Every `(k, v)` pair in the Cartesian product `[ (k, v) for k in keys for v in vals ]` is applied in order, and the total count of `(k, v)` pairs applied in this `"ingest"` call is appended to results.
- **Bracket Path Parsing (`k`)**:
  - A key consists of a non-empty root name followed by zero or more bracket segments `[subkey]` or `[]`, e.g. `user[roles][]` -> `["user", "roles", ""]`.
  - Raising `ValueError`: If the root name is empty (e.g. `[a]`), brackets are unbalanced/unclosed, characters appear after `]` outside brackets, or an empty push segment `[]` appears anywhere **except** the very last segment (e.g. `a[][b]` is invalid).
  - If an `"ingest"` operation raises `ValueError` at any point, `state` **must remain unmodified** (transactional rollback for that operation).
- **Applying `(path, v)` to `state`**:
  - Traverse/create intermediate dictionaries for all segments before the last segment.
  - If the last segment is `""` (from trailing `[]`), the target container at the parent segment must be a `list` (created as `[]` if missing, or replacing a non-list value if overwritten), and `v` is appended to it.
  - If the last segment is a non-empty string `s`, set `target[s] = v` (overwriting any previous scalar, dict, or list at `s`). If an intermediate segment on the path currently holds a scalar or a `list` instead of a `dict`, raise `ValueError`.
- `{"op": "unset", "key": str}`:
  - Expand `key` with brace expansion. For each expanded key path (which must not end in `[]`, otherwise raise `ValueError`), delete the target key if present and clean up any ancestor dictionaries that become empty as a result. Append the count of keys that actually existed and were deleted.
- `{"op": "snapshot"}`:
  - Append a deep copy of the current `state` dictionary.
- `{"op": "reset"}`:
  - Clear `state` to `{}` and append `None`.

### Example
```python
run_query_session([
    {"op": "ingest", "query": "f[{a,b}][]=1&f[a][]=2"},
    {"op": "snapshot"}
])
# Returns: [3, {"f": {"a": ["1", "2"], "b": ["1"]}}]
```
