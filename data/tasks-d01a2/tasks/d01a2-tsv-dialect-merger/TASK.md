Fix `merge_dialect_tables(primary_csv, secondary_tsv, key_col, prefer="latest")` in `solution.py`.

Parse two tables in different delimiter dialects, normalize headers, coerce values, and outer-join them on a normalized key column with deterministic conflict resolution.

### Specification
1. **Dialect Rules**:
   - `primary_csv` uses delimiter `","` and quote char `"\""`.
   - `secondary_tsv` uses delimiter `"\t"` and quote char `"\""`.
   - Normalize `\r\n` to `\n`. Outside quotes, lines whose first non-space (`' '`) character is `'#'` or that contain only spaces (`' '`) are ignored. Note: `'\t'` is a delimiter in `secondary_tsv`, so a line starting with `'\t'` in `secondary_tsv` is NOT blank—it starts with an empty first field!
   - Inside double quotes (`"..."`), delimiters, newlines, and `#` are literal, and `""` escapes a single `"`. For unquoted fields, strip leading/trailing spaces (`' '`). For quoted fields, strip spaces (`' '`) outside the quotes, preserve everything inside literally, and raise `ValueError` on unclosed quotes or extra non-space characters after the closing quote.
2. **Headers & Key Validation**:
   - The first non-ignored record of each table is its header row (each table must have a header row; raise `ValueError` if either table has no header row or has duplicate normalized headers within the same table).
   - Normalize every header name (and the `key_col` argument) by lowercasing, replacing runs of non-alphanumeric characters with `"_"`, and stripping leading/trailing `"_"`.
   - The normalized `key_col` must exist in BOTH tables' normalized headers; otherwise raise `ValueError`.
3. **Value Coercion & Primary Keys**:
   - Every data row must match its table's header length (else raise `ValueError`).
   - Unquoted empty string `""` or unquoted `"NULL"` (case-sensitive) coerces to `None`. Quoted `""` or `"NULL"` remains `str`.
   - Other unquoted strings matching `[+-]?\d+` with no redundant leading zeros (except `"0"`, `"+0"`, `"-0"`) coerce to `int`; all other values remain `str`.
   - The value of `key_col` in every row must not be `None` or `""` (raise `ValueError`), and is always converted to `str` for matching and output (e.g. `101` and `"101"` both become key `"101"`).
   - Within a single table, if multiple rows share the same key, merge them top-to-bottom where later non-`None` values overwrite earlier values (a later `None` does NOT overwrite an earlier non-`None` value).
4. **Merging Across Tables**:
   - Validate `prefer in ("primary", "secondary", "latest")`; raise `ValueError` otherwise.
   - Output columns are the union of normalized headers from both tables.
   - For each key present in either table, combine the deduplicated row from `primary_csv` and `secondary_tsv`. For any non-key column present in both tables:
     - If one table has `None` (or lacks the column) and the other has a non-`None` value, use the non-`None` value.
     - If both have non-`None` values:
       - `prefer == "primary"`: use `primary_csv`'s value.
       - `prefer == "secondary"` or `prefer == "latest"`: use `secondary_tsv`'s value.
   - Return the merged rows sorted by key: if all keys across the result are valid integers (`[+-]?\d+`), sort by `int(key)` ascending; otherwise sort by `key` lexicographically (`str` ascending).

### Example
```python
merge_dialect_tables(
    "ID,Score,Tag\n2,10,alpha\n1,20,NULL",
    "id\tscore\textra\n1\t25\tx\n2\tNULL\ty",
    "ID",
    prefer="latest"
)
# [{'extra': 'x', 'id': '1', 'score': 25, 'tag': None},
#  {'extra': 'y', 'id': '2', 'score': 10, 'tag': 'alpha'}]
```
