Fix `match_glob(pattern, path)` in `solution.py`.

Match a POSIX path string `path` against glob `pattern` (both split by `/` into path segments). Return `True` if the entire path matches, else `False`.

Supported syntax:
- `*`: matches 0 or more characters within a single segment (never crosses `/`).
- `?`: matches any single character within a single segment (never crosses `/`).
- `**`: when appearing as an entire segment (no other characters in that segment), matches 0 or more complete segments. Inside a segment (e.g. `a**b`), `**` behaves like `*`.
- Character classes `[...]`: matches 1 character within a segment:
  - Ranges `a-z` match `ord(a) <= ord(ch) <= ord(z)` (`ValueError` if `ord(a) > ord(z)`).
  - Leading `!` or `^` negates the class.
  - A `]` immediately after `[` (or `[!`, `[^`) is treated as a literal `]` rather than closing the class.
  - A `-` at the start (after `[`, `[!`, `[^`, or literal leading `]`) or directly before `]` is literal `-`.
- Backslash `\c` outside `[...]` escapes the next character literally.

Raise `ValueError` on unclosed `[`, empty class `[]` / `[!]` / `[^]`, descending range `[z-a]`, or trailing unescaped `\`.

Example:
```python
match_glob("src/**/test_[!0-9]*.py", "src/test_app.py")  # -> True
```
