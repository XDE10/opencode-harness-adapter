Fix `run_lexer(ops)` in `solution.py`.

Implement a stateful POSIX-like command stream lexer that processes a sequence of operations (`ops`) and returns a list of outputs corresponding to each operation.

### Lexer Rules
The lexer maintains a current mode (`"normal"`, `"single"`, or `"double"`), a trailing-backslash escape flag, and an in-progress token buffer across `"feed"` operations until `"flush"` or `"reset"` is called.

1. **Unquoted mode (`"normal"`)**:
   - Whitespace (`' '`, `'\t'`, `'\n'`) delimits tokens. If a token is currently active, emit it and reset the active token state; extra whitespace produces no tokens.
   - `'#'` starts a comment **only** when no token is currently active (i.e. at the beginning of a line or immediately after whitespace/comment). A comment discards all characters up to (but not including) the next `'\n'`. An inline `'#'` attached to an active token (e.g. `foo#bar`) is treated as a literal `'#'` character.
   - `'\'` escapes the very next character (even across chunk boundaries):
     - `'\'` followed by `'\n'` is a line continuation and is completely ignored (neither character is added to the token, nor does it start a token).
     - `'\'` followed by any other character `c` starts/continues an active token and appends literal `c`.
   - `"'"` starts/continues an active token and switches to `"single"` quote mode.
   - `'"'` starts/continues an active token and switches to `"double"` quote mode.
   - Any other character starts/continues an active token and appends itself.
   - Note: empty quotes like `""` or `''` still activate a token so that `""` emits `""`.

2. **Single-quote mode (`"single"`)**:
   - All characters are taken literally (backslashes have no special meaning) until the closing `"'"`, which returns to `"normal"` mode.

3. **Double-quote mode (`"double"`)**:
   - `'"'` returns to `"normal"` mode (unless escaped).
   - `'\'` inside double quotes only acts as an escape if the next character (even in a subsequent `"feed"` chunk) is `'"'`, `'\'`, `'$'`, ``'`'``, or `'\n'`:
     - If followed by `'\n'`, both the backslash and newline are removed (line continuation).
     - If followed by `'"'`, `'\'`, `'$'`, or ``'`'``, only that second character is appended.
     - If followed by any other character `c`, **both** `'\\'` and `c` are appended literally.

### Operations
- `{"op": "feed", "chunk": str}`: Process `chunk` character-by-character, append any completed tokens to an output list for this operation, and append that list of newly completed tokens to results.
- `{"op": "flush"}`: Finish the current stream.
  - If currently inside `"single"` or `"double"` quote mode, or if a trailing unescaped `'\\'` is still pending, raise `ValueError` **and reset** the lexer state back to clean `"normal"` mode with no active token.
  - Otherwise, if a token is active, emit it in a single-element list `[token]` and reset the active token; if no token is active, emit `[]`.
- `{"op": "reset"}`: Discard any partial token, quote mode, comment state, or pending escape, and append `None` to results.
- Unknown `"op"` values must raise `ValueError`.

### Example
```python
run_lexer([
    {"op": "feed", "chunk": "echo '' foo#1 # comment\nbar"},
    {"op": "flush"}
])
# Returns: [[ "echo", "", "foo#1" ], [ "bar" ]]
```
