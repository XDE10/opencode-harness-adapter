Fix `wrap_hanging(text, width=72, indent=0, hanging_indent=4, break_long_words=False)` in `solution.py`.

Wraps multi-paragraph text using a first-line indent and a hanging indent for continuation lines.

Validation rules (raise `ValueError` on invalid input):
- `text` must be a `str`.
- `width` must be an `int >= 1` (not `bool`).
- `indent` and `hanging_indent` must be `int >= 0` (not `bool`).
- `break_long_words` must be a `bool`.
- `width > indent` and `width > hanging_indent`.

Paragraph & wrapping rules:
- Normalize `\r\n` to `\n`. Split into paragraphs on one or more blank (whitespace-only) lines, ignoring leading and trailing blank lines. If `text` contains only whitespace, return `""`.
- Within each paragraph, split on whitespace (`para.split()`) into words.
- Line 0 of each paragraph uses prefix `" " * indent` (available width `width - indent`); lines 1+ use prefix `" " * hanging_indent` (available width `width - hanging_indent`).
- Pack words greedily separated by a single space so that `len(cur) + 1 + len(word) <= avail`.
- If a word exceeds the current line's available width (`len(word) > avail`):
  - When `break_long_words=False`: flush the current line if non-empty, then place the intact word on its own line with that line's prefix.
  - When `break_long_words=True`: flush the current line if non-empty, then split the word sequentially into chunks fitting each line's available width (so the first chunk uses `width - indent` if it begins on line 0, and subsequent chunks use `width - hanging_indent`).
- Join paragraphs with `"\n\n"` and return the resulting string.

Example:
`wrap_hanging("alpha beta gamma", width=10, indent=0, hanging_indent=2)`
returns `"alpha beta\n  gamma"`.
