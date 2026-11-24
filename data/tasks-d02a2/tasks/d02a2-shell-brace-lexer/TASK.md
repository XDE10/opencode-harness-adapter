Fix `tokenize_command(cmd, env)` in `solution.py`.

Implement a shell-like command tokenizer supporting quoting, variable interpolation, and top-level brace expansion:

1. **Token Separation & Quoting**:
   - Outside quotes, whitespace (`' '`, `'\t'`, `'\n'`) separates tokens. Consecutive whitespace is collapsed.
   - An adjacent quoted empty string (e.g. `""` or `''`) still produces a token (possibly `""` if standalone).
   - **Single quotes (`'...'`)**: All characters inside are treated literally (no backslash escapes, no `$VAR` expansion, no `{a,b}` brace expansion). Raise `ValueError` if unclosed.
   - **Double quotes (`"..."`)**: Supports backslash escapes for `\"`, `\\`, `\$`, `\{`, `\}` (any other `\x` inside double quotes keeps both `\` and `x`), and supports `$VAR` / `${VAR}` expansion. Commas and braces inside double quotes are treated as literal characters (do **not** trigger brace expansion). Raise `ValueError` if unclosed.
   - **Unquoted**: A backslash `\x` escapes any next character `x` literally (disabling whitespace splitting, quotes, `$`, `{`, `,`, `}`). A trailing lonely `\` at the end of `cmd` raises `ValueError`.

2. **Variable Interpolation (`$VAR` and `${VAR}`)**:
   - Allowed unquoted or inside double quotes (when `$` is not escaped).
   - `${NAME}` reads up to the next `}` (raise `ValueError` if unclosed or `NAME` is not a valid identifier matching `[A-Za-z_][A-Za-z0-9_]*`).
   - `$NAME` reads the longest valid identifier `[A-Za-z_][A-Za-z0-9_]*` immediately following `$`. If `$` is not followed by `{` or a valid identifier start character, treat `$` as a literal `'$'`.
   - Look up `NAME` in `env` (`dict[str, str]`), defaulting to `""` if missing. Expanded values are literal text (they do **not** undergo word splitting or brace expansion).

3. **Unquoted Brace Expansion (`prefix{a,b,c}suffix`)**:
   - Each token may contain at most one unquoted, unescaped `{...}` group containing **at least one unquoted/unescaped comma `,`**.
   - If a `{...}` block has no unquoted/unescaped comma (e.g. `{solo}` or `{}`), its braces are treated as literal characters `{` and `}`.
   - If an unquoted `{` has no matching unquoted `}` within the same token, treat it as literal `{`.
   - When a valid `{alt1,alt2,...}` group is present in a token, expand the token into `prefix + alt + suffix` for each comma-separated alternative in left-to-right order (empty alternatives like `{a,}` are valid).

Examples:
- `tokenize_command('echo "hi $USER" {a,b}.txt', {"USER": "ada"})` -> `["echo", "hi ada", "a.txt", "b.txt"]`
- `tokenize_command('cmd "" {only}', {})` -> `["cmd", "", "{only}"]`
