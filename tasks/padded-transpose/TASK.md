# Transpose a grid with uneven rows

Fix `transpose_padded(rows, fill=None)` in `solution.py`.

Return a list of columns. Use the longest row to determine the number
of columns, and put fill where a row does not have that column. Preserve
every actual cell, including null. Empty rows still occupy positions
in every column. If there are no cells, return an empty list.
