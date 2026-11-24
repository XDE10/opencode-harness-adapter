Fix `filter_records(records, query)` in `solution.py`.

Filter `records` (a list of `dict`s, each containing `"id"`) against boolean search `query`, returning matching `"id"` values in input order.

Boolean grammar (highest to lowest precedence):
- Parentheses `(...)`
- `NOT <expr>` (right-associative, chainable like `NOT NOT ...`)
- `<expr> AND <expr>` (left-associative)
- `<expr> OR <expr>` (left-associative)
Keywords `AND`, `OR`, `NOT` are case-sensitive uppercase.

Predicates:
- `has:<field>`: `True` iff `<field>` is present in the record and not `None`.
- `<field>:<value>`: `<value>` is an unquoted non-whitespace token (stopping before `)`), or `'...'` / `"..."` quoted string.
  - If `record[field]` is a `list`, matches if any item equals `<value>` (comparing `bool` as `"true"`/`"false"`, `int` as decimal string, `str` directly).
  - If `record[field]` is a `bool`, matches `"true"`/`"false"` (case-insensitive).
  - If `record[field]` is an `int` (not `bool`), matches integer value of `<value>` (or `False` if `<value>` is not an integer).
  - If `record[field]` is a `str`, matches exact string `<value>`.
- `<field>~<substr>`: case-insensitive substring match against `str` field or any `str` element of a `list` field.
- `<field>=<int>`, `<field>>=<int>`, `<field><=<int>`, `<field>><int>`, `<field><<int>`: integer comparison; `False` if missing, `None`, `bool`, or non-`int`.

Raise `ValueError` on empty queries, unmatched parentheses, unclosed quotes, missing operands, invalid numeric values, or invalid predicate syntax.

Example:
```python
filter_records([{"id": 1, "env": "prod", "err": 0}], "env:prod AND err=0")  # -> [1]
```
