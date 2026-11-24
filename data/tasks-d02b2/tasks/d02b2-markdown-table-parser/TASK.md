Fix `parse_markdown_table(lines)` in `solution.py`.

Parse a list of strings representing a Markdown table into a dictionary describing its headers, column alignments, and body rows.

### Specification
1. **Input cleanup**:
   - Ignore any leading or trailing lines in `lines` that are empty or contain only whitespace.
   - If fewer than 2 non-empty lines remain (a header line and a delimiter line), or if any blank line appears *between* non-empty table lines, raise `ValueError`.

2. **Row splitting (`split_row`)**:
   - Strip leading and trailing whitespace from the line.
   - If the line starts with an unescaped `|`, remove that single leading `|`.
   - If the line ends with an unescaped `|` (i.e. a trailing `|` preceded by an **even** number of consecutive backslashes `\`), remove that single trailing `|`.
   - Split the remaining text into raw cells on unescaped `|` characters (a `|` is escaped if preceded by an odd number of consecutive backslashes).
   - Inside each cell:
     - **Backtick code spans**: Content enclosed in single backticks `` `...` `` protects `|` from splitting the cell and preserves backslashes literally (do not unescape `\|` or `\\` inside code spans). Unclosed backticks treat the rest of the cell as normal text (not a code span).
     - Outside code spans, unescape `\|` to `|` and `\\` to `\`. Any other `\x` sequence remains `\x`.
     - Strip leading and trailing whitespace from the resulting cell string.

3. **Header & Delimiter validation**:
   - The first non-empty line is the header row; let `N` be its cell count (`N >= 1`).
   - The second non-empty line is the delimiter row. It must have exactly `N` cells.
   - Each delimiter cell (after whitespace stripping) must consist of optional `:`, followed by **at least 3** dashes (`---`), followed by optional `:`. Any other characters or fewer than 3 dashes must raise `ValueError`.
   - Alignment for each column is:
     - `"center"` if both leading and trailing `:` are present (`:---:`)
     - `"right"` if only trailing `:` is present (`---:`)
     - `"left"` otherwise (`---` or `:---`)

4. **Body rows**:
   - Each subsequent line is split into cells using the same row-splitting rules.
   - If a body row has **fewer** than `N` cells, pad it on the right with empty strings `""` up to length `N`.
   - If a body row has **more** than `N` cells, raise `ValueError`.

5. **Return value**:
   Return `{"headers": list[str], "align": list[str], "rows": list[list[str]]}`.

### Example
```python
parse_markdown_table([
    "| Name | Expr | Score |",
    "| :--- | :---: | ---: |",
    "| Alice | `a | b` | 10 |",
    "| Bob\\|Jr | x \\| y |",
])
# Returns:
# {
#   "headers": ["Name", "Expr", "Score"],
#   "align": ["left", "center", "right"],
#   "rows": [
#     ["Alice", "`a | b`", "10"],
#     ["Bob|Jr", "x | y", ""]
#   ]
# }
```
