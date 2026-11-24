Fix `parse_query_string(query)` in `solution.py`.

Parse a URL query string with nested bracket notation (e.g. `user[name]=ada&tags[]=a&tags[]=b`) into a nested dictionary of strings, lists, and dicts.

1. **Splitting & Percent-Decoding**:
   - Strip a single leading `'?'` if `query` starts with `'?'`. If the remaining string is empty, return `{}`.
   - Split raw segments on `'&'`. Ignore empty segments (such as leading/trailing `'&'` or `'&&'`).
   - Within each segment, split on the **first** `'='` into `(raw_key, raw_val)`. If `'='` is absent, `raw_key` is the whole segment and `raw_val` is `""`.
   - Decode both `raw_key` and `raw_val` by replacing `'+'` with `' '` and decoding `%XX` hex sequences into UTF-8 characters. Note: percent-encoded `%26` (`&`), `%3D` (`=`), `%5B` (`[`), and `%5D` (`]`) are decoded **after** splitting on `&` and `=`, and brackets in the decoded key ARE treated as bracket syntax. If any `%` is not followed by two valid hex digits, raise `ValueError`.

2. **Bracket Path Syntax**:
   - A decoded key consists of a non-empty root key name (containing no `[` or `]`) followed by zero or more bracket segments `[subkey]`.
   - Every `[` must be matched by a `]`, and bracket segments must be immediately adjacent up to the end of the key (e.g., `a[b][c]` or `a[][b]`).
   - Raise `ValueError` if:
     * the root name is empty (e.g. `[a]=1` or `=1`),
     * brackets are unclosed, stray, nested like `a[[b]]`, or have trailing characters after `]` (e.g. `a[b]c=1`),
     * an empty bracket `[]` (list append) is directly followed by another `[]` (`a[][]=1` is invalid).

3. **Tree Construction & Conflict Rules**:
   - A non-empty segment `[k]` indexes into a `dict` at key `k` (always as a string key, even if `k` is numeric).
   - An empty segment `[]` appends to a `list`.
   - When `[]` is followed by `[k]` (e.g. `items[][id]=1&items[][name]=x&items[][id]=2`), inspect the last element of the list:
     * If the list is empty, or its last element is not a `dict`, or `k` already exists in the last element's sub-tree at the target path (for a terminal `[k]`, if `k in last_dict`), append a new `{}` to the list and insert into it.
     * Otherwise, reuse the last `dict` in the list and insert into it.
   - If a scalar value is assigned to an existing scalar key in a `dict`, the later value overwrites the earlier scalar value.
   - **Type Conflict**: If any step tries to index into a scalar (`str`) as a `dict` or `list`, or tries to use a `list` as a `dict` or a `dict` as a `list`, or tries to overwrite an existing `dict` or `list` with a scalar, raise `ValueError`.

Examples:
- `parse_query_string("a[x]=1&a[y]=2&b[]=u&b[]=v")` -> `{"a": {"x": "1", "y": "2"}, "b": ["u", "v"]}`
- `parse_query_string("users[][id]=1&users[][role]=admin&users[][id]=2")` -> `{"users": [{"id": "1", "role": "admin"}, {"id": "2"}]}`
