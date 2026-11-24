Fix `run_csv_stream(delimiter, ops)` in `solution.py`.

Implement a stateful incremental CSV/custom-delimiter parser session that receives arbitrary text chunks across operations, normalizes the first non-comment record as a header, coerces field values, and emits parsed row dictionaries.

### Parameters
- `delimiter`: A single-character string (cannot be `"\n"`, `"\r"`, `'"'`, or `"#"`). Raise `ValueError` if `delimiter` is invalid.
- `ops`: A list of operation dictionaries:
  1. `{"op": "feed", "chunk": str}`: Append `chunk` to the internal parser buffer, process any complete records terminated by `"\n"`, and append the number of newly completed data rows (excluding the header and comment/blank records) to the results list.
  2. `{"op": "finish"}`: Flush any remaining non-empty trailing record in the buffer as if followed by `"\n"`. If the parser is still inside an unclosed double-quoted field, raise `ValueError`. Append the number of newly completed data rows to the results list.
  3. `{"op": "take"}`: Drain and append all accumulated completed data row dicts (in order) to the results list, clearing the internal completed-rows queue (while preserving the current header and any partial unparsed buffer).
  4. `{"op": "reset"}`: Clear the internal buffer, quote state, header, and any un-drained completed data rows, and append `None` to the results list.

### Parsing & Normalization Rules
- **Quotes & Escapes**: Double quotes (`"`) enclose fields that may contain `delimiter`, `"\n"`, or `"#"`. Inside a double-quoted field, a literal double quote is escaped by doubling it (`""`).
- **Comments & Blank Records**: An unquoted record whose raw text (before splitting) is empty, whitespace-only, or starts with `"#"` after leading spaces/tabs (only when the `"#"` itself is not inside quotes) is ignored and produces neither a header nor a data row.
- **Header Normalization**: The first non-ignored record defines the column headers. Each header name is stripped of surrounding whitespace, lowercased, and internal runs of whitespace or `"-"` are replaced with a single `"_"`. Duplicate or empty normalized header names must raise `ValueError`.
- **Data Rows & Type Coercion**: Every subsequent non-ignored record must have the exact same number of fields as the header (otherwise raise `ValueError`).
  - Unquoted fields are stripped of leading/trailing spaces; quoted fields preserve inner leading/trailing spaces after quote removal.
  - Empty unquoted fields (`""`) coerce to `None`, whereas an explicitly quoted empty string (`""""`) coerces to `""`.
  - Unquoted case-insensitive `"true"` / `"false"` coerce to `True` / `False`.
  - Unquoted optional-sign base-10 integers (e.g. `"0"`, `"-42"`, `"105"`) coerce to `int`.
  - All other fields remain `str`.

### Example
```python
run_csv_stream(",", [
    {"op": "feed", "chunk": "Item-Name,Qty\n# comment\napple,10\n\"pear"},
    {"op": "feed", "chunk": "\nfresh\",0\n"},
    {"op": "take"}
])
# Returns: [1, 1, [{"item_name": "apple", "qty": 10}, {"item_name": "pear\nfresh", "qty": 0}]]
```
