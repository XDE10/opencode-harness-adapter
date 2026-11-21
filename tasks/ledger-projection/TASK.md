# Keep empty cells during a ledger export

Fix `project_rows(rows, columns, default=None)` in `solution.py`.

Rows are lists and columns is a list of nonnegative column indexes in
export order. Return a new list of rows, including repeated indexes. A
missing index gets default. Present cells, including 0, false, an empty
string, and null, keep their value. With no columns, return one empty row
for each input row.
