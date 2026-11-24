Fix `render_box_table(headers, rows, col_widths=None, padding=1)` in `solution.py`.

Renders an ASCII box-drawing table as a single newline-joined string using `+`, `-`, and `|`.

Validation rules (raise `ValueError` on invalid input):
- `headers` must be a non-empty `list[str]`.
- `rows` must be a `list` of `list[str]`, and each row must have `len(row) == len(headers)`.
- `padding` must be a non-negative `int` (not `bool`).
- `col_widths`, if not `None`, must be a `list[int]` (no `bool`) with `len(col_widths) == len(headers)` and every width `>= 1`.

Layout & wrapping rules:
- Each cell string is first split on `"\n"` into lines.
- If `col_widths` is `None`, each column width is `max(1, max(len(line) for all header and row cell lines in that column))` with no word wrapping.
- If `col_widths` is provided, each line of each cell (including headers) is wrapped to its column width `w`:
  - Empty lines remain `[""]`.
  - Split on whitespace into words and pack greedily with a single space (`len(cur) + 1 + len(word) <= w`).
  - Any single word longer than `w` is placed on its own line and hard-split into chunks of at most `w` characters.
- For each row (header or data), its rendered height is the maximum wrapped line count across its cells; shorter cells are padded at the bottom with `""`.
- Each horizontal border is `"+" + "+".join("-" * (w + 2 * padding) for w in widths) + "+"`.
- Each content line is `"|" + "|".join((" " * padding) + line.ljust(w) + (" " * padding) for line, w in zip(row_lines, widths)) + "|"`.
- Emit: top border, header lines, header separator border, and for each data row its content lines followed by a border.

Example:
`render_box_table(["A", "B"], [["1", "2"]])` returns:
`"+---+---+\n| A | B |\n+---+---+\n| 1 | 2 |\n+---+---+"`.
