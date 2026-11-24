Fix `parse_markdown_table(text, trim=True, unescape=True)` in `solution.py`.

`text` is a multi-line Markdown table string. Returns a `list[dict[str, str]]` where each dictionary maps header column names to the corresponding row cell values.

Parsing & validation rules:
- If `text` is not a `str`, raise `ValueError`.
- Split on `\n` (stripping trailing `\r` on each line). Ignore leading and trailing blank (whitespace-only) lines; any blank line *between* the first and last non-empty lines raises `ValueError`.
- At least 2 non-empty lines (header and separator) are required; otherwise raise `ValueError`.
- Split each line on unescaped `|` delimiters (a `|` preceded by an even number of consecutive backslashes is a delimiter; an odd number escapes `|`). Strip optional leading and trailing unescaped outer `|` delimiters from the trimmed line.
- Separator row (`lines[1]`) must have the exact same column count as the header row, and each stripped cell must match `^:?-{3,}:?$`; otherwise raise `ValueError`.
- When `trim=True`, strip leading and trailing whitespace from every header and body cell. When `trim=False`, preserve cell whitespace as-is.
- When `unescape=True`, perform a single left-to-right pass replacing `\\` with `\` and `\|` with `|` (leaving any other `\x` sequence untouched). Do this *after* trimming.
- After trimming and unescaping, every header name must be non-empty and all header names must be unique; otherwise raise `ValueError`.
- Body rows with more cells than headers raise `ValueError`; body rows with fewer cells than headers are padded with `""`.

Example:
`parse_markdown_table("| k | v |\n| --- | --- |\n| a\\|b | 1 |")`
returns `[{"k": "a|b", "v": "1"}]`.
