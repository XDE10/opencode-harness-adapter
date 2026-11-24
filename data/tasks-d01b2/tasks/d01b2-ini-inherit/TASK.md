Fix `parse_ini(text)` in `solution.py`.

Implement a parser for an INI configuration format with section inheritance, quoted strings, inline comments, and `${section.key}` / `${key}` interpolation.

### Syntax Rules
1. **Lines & Comments**:
   - Split input on `\n` (strip any trailing `\r`).
   - Outside of double quotes, `#` or `;` starts an inline comment through the end of the line.
   - Blank or comment-only lines are ignored.
   - Key-value entries appearing before the first section header belong to the `"default"` section.
2. **Section Headers**:
   - After stripping inline comments and outer whitespace, a line starting with `[` and ending with `]` declares a section:
     - `[name]` or `[name : parent]` (whitespace around `name`, `:`, and `parent` is stripped).
     - Section names and parent names must be non-empty and match `[A-Za-z0-9_-]+`; otherwise raise `ValueError`.
     - Re-opening an already declared section merges subsequent keys into it; if a parent is specified when re-opening, it must match any previously declared parent for that section (or set it if none was set), otherwise raise `ValueError`.
3. **Key-Value Pairs**:
   - Format: `key = value` (split on the first `=`). If a non-empty line has no `=`, raise `ValueError`.
   - `key` (stripped of whitespace) must match `[A-Za-z0-9_.-]+`; otherwise raise `ValueError`.
   - After stripping comments and leading/trailing whitespace from `value`:
     - If `value` starts with `"`, it must also end with `"` (len >= 2), with no unescaped `"` inside, and supports escape sequences `\"`, `\\`, `\n`, `\t` (any other `\x` raises `ValueError`, and a trailing unescaped `\` before the closing quote raises `ValueError`).
     - If unquoted, it may not contain `"` (raise `ValueError`), and its stripped text is used literally.
4. **Inheritance**:
   - After parsing all lines, every section with a `: parent` inherits any keys not explicitly set in the child from its `parent` chain (transitively).
   - If a referenced `parent` section was never declared (Note: `"default"` exists only if explicitly declared with `[default]` or if top-level keys were defined before the first section header), or if the section inheritance graph contains a cycle, raise `ValueError`.
5. **Variable Expansion**:
   - Every value may contain `${target}` placeholders:
     - `${key}` looks up `key` in the current section (including inherited keys).
     - `${sec.key}` (split on the first `.` if `sec` is a valid existing section name; if `target` contains `.` where the prefix before the first `.` is an existing section, resolve `key` in `sec`; otherwise look up the full `target` as a key in the current section, and if not found, raise `KeyError`).
     - If a referenced section or key does not exist, raise `KeyError`.
     - Expansions are resolved transitively. If variable expansion encounters a cycle (e.g., `a = ${b}`, `b = ${a}`), raise `ValueError`.

Return a `dict[str, dict[str, str]]` mapping each declared section name (including `"default"` if it has keys or was explicitly declared via `[default]`) to its resolved `key -> str` mapping.

### Example
```python
text = """
[base]
host = localhost
url = http://${host}:${port}

[prod : base]
port = 8080
"""
parse_ini(text)
# Returns:
# {
#   "base": ... (raises KeyError if base.url is evaluated without port, so base only valid if all its keys resolve!)
# }
```
Wait: every key present in every returned section (including base sections) is fully resolved; for example:
```python
parse_ini("[base]\nhost = 127.0.0.1\nport = 80\nurl = ${host}:${port}\n[app : base]\nport = 9000\n")
# {"base": {"host": "127.0.0.1", "port": "80", "url": "127.0.0.1:80"},
#  "app":  {"host": "127.0.0.1", "port": "9000", "url": "127.0.0.1:9000"}}
```
