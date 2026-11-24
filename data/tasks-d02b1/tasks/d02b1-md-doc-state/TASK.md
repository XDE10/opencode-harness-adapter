Fix `run_markdown_session(ops)` in `solution.py`.

Implement a stateful Markdown document processor that tracks heading slugs and footnote numbering across a sequence of operations.

`ops` is a list of operation dicts. Process them in order and return a list containing the result of each operation:

1. `{"op": "heading", "level": int, "text": str}`
   - `level` must be an integer between `1` and `6` inclusive; otherwise raise `ValueError`.
   - Generate a base slug from `text`:
     1. Strip inline code backticks (remove all `` ` `` characters), then convert to lowercase.
     2. Replace any sequence of one or more characters that are NOT lowercase ASCII letters (`a-z`), ASCII digits (`0-9`), or spaces (` `) with nothing (i.e. remove punctuation/symbols; note that hyphens `-` are kept as spaces or wait: keep existing hyphens `-` as hyphens!).
     Specifically:
     - First remove all `` ` `` characters and lowercase the string.
     - Keep only `a-z`, `0-9`, spaces `' '`, and hyphens `'-'`; remove all other characters.
     - Collapse any run of one or more spaces and/or hyphens (`[ -]+`) into a single hyphen `'-'`, and strip leading/trailing hyphens `'-'`.
     - If the resulting base slug is empty, use `"section"`.
   - Deduplication:
     - Maintain a count of how many times each **base slug** has been generated in the current document session, AND a set of all **final slugs** already emitted in the session.
     - On the first occurrence of `base`, if `base` is not already in the emitted set, the final slug is `base`.
     - Otherwise, try `f"{base}-{k}"` starting from `k = 1, 2, ...` until finding a candidate not yet in the emitted set.
     - Record the final slug in the emitted set and return `{"level": level, "slug": final_slug}`.

2. `{"op": "footnote_def", "label": str, "text": str}`
   - `label` is normalized by stripping leading/trailing whitespace and lowercasing. If the normalized label is empty, raise `ValueError`.
   - Define or update the footnote content `text` (stripped of leading/trailing whitespace) for that normalized label.
   - Updating an already-defined footnote updates its `text` in place without changing any assigned footnote number.
   - Return `None`.

3. `{"op": "render_line", "line": str}`
   - Replace every footnote reference of the form `[^label]` in `line` (outside inline code spans delimited by single backticks `` `...` ``):
     - Inline code spans start at a `` ` `` and end at the next matching `` ` `` on the same line. Inside a code span, `[^label]` is left untouched. An unclosed single `` ` `` has no code span and is treated as a literal character.
     - For each `[^label]` outside code spans (where `label` contains one or more characters other than `]` and `` ` ``):
       - Normalize `label` (strip and lowercase).
       - If the normalized label has NOT been defined via `footnote_def` in the current session, raise `KeyError`.
       - If the normalized label has not yet been referenced by a successful `render_line`, assign it the next sequential integer starting from `1` (`1, 2, 3, ...`) in order of first reference.
       - Note: If a line contains an undefined footnote label and raises `KeyError`, no state changes (no new numbers assigned) from that failing `render_line` operation may persist!
       - Replace `[^label]` with `[num]`.
   - Return the rendered line string.

4. `{"op": "export"}`
   - Return `{"toc": [...], "footnotes": [...]}` where:
     - `"toc"` is the list of `{"level": int, "slug": str}` dicts emitted so far in order.
     - `"footnotes"` is the list of `[num, text]` pairs for all **referenced** footnotes only, ordered by `num` ascending (`1, 2, ...`). Unreferenced definitions are excluded.

5. `{"op": "reset"}`
   - Clear all headings, slug history, footnote definitions, and footnote reference numbers, and return `None`.

Unknown `"op"` values must raise `ValueError`.

Example:
```python
run_markdown_session([
    {"op": "heading", "level": 1, "text": "Intro!"},
    {"op": "heading", "level": 2, "text": "Intro?"},
    {"op": "footnote_def", "label": "A", "text": "First note"},
    {"op": "render_line", "line": "See [^a] and `[^a]`."},
    {"op": "export"}
])
```
returns:
```python
[
    {"level": 1, "slug": "intro"},
    {"level": 2, "slug": "intro-1"},
    None,
    "See [1] and `[^a]`.",
    {"toc": [{"level": 1, "slug": "intro"}, {"level": 2, "slug": "intro-1"}], "footnotes": [[1, "First note"]]}
]
```
