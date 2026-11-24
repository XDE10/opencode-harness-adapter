Implement/fix `parse_dotenv(text, overrides=None)` in `solution.py`.

Parses `.env` configuration text and returns a dict mapping variable names to resolved string values.

Specification:
- Lines may use `\n` or `\r\n`. Blank lines and `#` comment lines (after leading whitespace) are ignored.
- An optional `export ` prefix (followed by one or more spaces/tabs) may precede `KEY=VALUE`.
- Non-empty, non-comment lines without `=` raise `ValueError`. Keys (trimmed) must match `[A-Za-z_][A-Za-z0-9_]*`, otherwise raise `ValueError`.
- Values support three quoting forms:
  - Single-quoted `'...'`: literal contents (no escape processing, no interpolation, `#` inside quotes is literal). Unclosed quotes or trailing non-comment text after the closing quote raise `ValueError`.
  - Double-quoted `"..."`: supports escapes `\n`, `\t`, `\r`, `\"`, `\\`, `\$`; supports variable interpolation; `#` inside quotes is literal. Unclosed quotes or trailing non-comment text after the closing quote raise `ValueError`.
  - Unquoted: any `#` at the start of the value or preceded by whitespace begins an inline comment; remaining leading/trailing whitespace is stripped. Supports `\$` escape and variable interpolation.
- Later definitions of the same key overwrite earlier ones.
- `overrides` (optional `dict[str, str]`) takes precedence over parsed keys as literal (non-interpolated) strings and is included in both interpolation lookups and the returned dict.
- Interpolation (in unquoted and double-quoted values):
  - `${VAR}` expands to `VAR`'s resolved value, or `""` if unset.
  - `${VAR:-default}` expands to `VAR` if set and non-empty (`!= ""`), otherwise recursively expands `default`.
  - `${VAR-default}` expands to `VAR` if set (even if `""`), otherwise recursively expands `default`.
  - Unclosed `${` or cyclic variable references raise `ValueError`. Repeated non-cyclic references like `${A}_${A}` must succeed.

Example:
```python
parse_dotenv('BASE=/opt\nURL="${BASE}/app" # ok\n', {"BASE": "/srv"})
# -> {"BASE": "/srv", "URL": "/srv/app"}
```
