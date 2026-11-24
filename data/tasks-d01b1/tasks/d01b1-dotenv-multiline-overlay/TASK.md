Fix `run_dotenv(ops)` in `solution.py`.

Implement a stateful `.env` configuration manager supporting layered environment scopes, triple-quoted multiline values, inline comments, and variable expansion with cycle detection.

`run_dotenv(ops)` accepts a list of operation dicts and returns a list of results:

1. `{"op": "parse", "layer": str, "text": str}`
   Parses dotenv content into the named `layer` (replacing any previous content of `layer` atomically).
   - Lines may have leading/trailing whitespace. Ignore blank lines and comment lines starting with `#`.
   - Each binding starts with an optional `export ` prefix (followed by at least one space), then `KEY=VALUE`.
   - `KEY` (stripped of spaces before `=`) must match `^[A-Za-z_][A-Za-z0-9_]*$`; otherwise raise `ValueError`.
   - `VALUE` starts immediately after `=` (strip leading horizontal spaces/tabs before checking quotes):
     * **Triple-quoted (`"""..."""`)**: May span multiple lines. Characters inside `"""..."""` are kept verbatim (including `#` and newlines) except `\"` and `\\` which unescape to `"` and `\`. After the closing `"""` on its closing line, only optional whitespace and an optional `#...` comment are permitted (otherwise raise `ValueError`). Unclosed `"""` raises `ValueError`.
     * **Single-quoted (`'...'`)**: Single-line literal string (no escape sequences, `#` is literal, and `${...}` inside single quotes must **not** be expanded later). Unclosed `'` or non-comment trailing characters on the line raise `ValueError`.
     * **Double-quoted (`"..."`)**: Single-line string supporting `\n`, `\"`, `\\` escapes and `${...}` expansion. `#` inside `"..."` is literal. After closing `"`, only optional whitespace and `#...` comment are allowed.
     * **Unquoted**: Single-line value. Strip an inline comment only when `#` is preceded by whitespace (` ` or `\t`) or is at index 0 of the unquoted value and followed by a space (Wait: specifically, in an unquoted value, `#` starts an inline comment if and only if it is preceded by whitespace ` ` or `\t`, or if the unquoted value starts with `# `). Actually: in an unquoted value, `#` starts an inline comment if and only if it is preceded by at least one whitespace character (` ` or `\t`) on the right-hand side of `=`, OR if `#` is the very first character after `=` (before stripping leading spaces after `=`, any space before `#` counts as preceding whitespace; if `#` is immediately after `=` with no space, like `SLUG=item#42` or `TAG=#v1`, `#` is literal!). Then strip leading and trailing whitespace. Supports `${...}` expansion.
   - Appends `"OK"`.

2. `{"op": "activate", "layers": list[str]}`
   Sets the active layer stack ordered from lowest priority to highest priority (later layers override earlier layers). If any layer name in `layers` has not been created via `parse`, raise `KeyError`. Appends `"OK"`.

3. `{"op": "resolve", "key": str}`
   Looks up `key` in the active layer stack (highest priority layer that defines `key` wins; if not defined in any active layer, return `None`).
   - If the winning entry was single-quoted, return its literal string without expanding `${...}`.
   - Otherwise expand `${VAR}` and `${VAR:-fallback}` against the **current active layer stack**:
     * If `VAR` is defined in the active stack and its resolved value is **non-empty**, use its resolved value.
     * If `${VAR:-fallback}` is used and `VAR` is either undefined in the active stack **or** resolves to `""` (empty string), use `fallback` (literal string).
     * If `${VAR}` (without `:-`) is used and `VAR` is undefined in the active stack, raise `KeyError`.
     * If variable expansion forms a cycle (e.g. `A=${B}`, `B=${A}`), raise `ValueError`.

4. `{"op": "export_all"}`
   Returns a dict of all keys present across all currently active layers mapped to their resolved values (sorted by key).

Example:
```python
run_dotenv([
    {"op": "parse", "layer": "base", "text": "HOST=localhost # default\nPORT=5432\nURL=${HOST}:${PORT}"},
    {"op": "activate", "layers": ["base"]},
    {"op": "resolve", "key": "URL"}
])
# returns ["OK", "OK", "localhost:5432"]
```
