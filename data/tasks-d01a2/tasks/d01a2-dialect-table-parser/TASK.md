Fix `parse_table(text, delimiter=",", null_tokens=("", "NULL", "N/A"))` in `solution.py`.

Parse a custom-delimited table with header normalization, comment lines, quoted fields, and type coercion into a list of row dicts.

### Specification
1. **Parameters & Validation**:
   - `delimiter`: must be a 1-character string other than `"\""`, `"#"`, `"\n"`, or `"\r"`; otherwise raise `ValueError`.
   - `null_tokens`: iterable of strings that represent missing values.
2. **Records & Comments**:
   - Line breaks outside double quotes are `\n` or `\r\n` (normalize `\r\n` to `\n` everywhere, including inside quotes).
   - Define horizontal padding characters as spaces (`" "`) and tabs (`"\t"`), EXCEPT `delimiter` itself (if `delimiter == "\t"`, only `" "` is padding; if `delimiter == " "`, only `"\t"` is padding).
   - Any physical record (outside of an open quoted field) whose first non-padding character is `#`, or which contains only padding characters before `\n` (or EOF), is ignored.
   - A `#` inside a quoted field, or in an unquoted field after the first non-padding character of the record, is treated as a literal character (NOT a comment).
3. **Field Parsing & Quotes**:
   - Unquoted fields have leading and trailing padding characters stripped. Quotes are not allowed inside an unquoted field.
   - A field becomes quoted if its first non-padding character is `"` (any padding characters before the opening `"` and after the closing `"` are discarded; non-padding characters after the closing `"` before the next delimiter/newline raise `ValueError`).
   - Inside a quoted field, all characters and newlines are preserved literally, and `""` (two double-quotes) decodes to a single `"`. An unclosed quoted field at EOF raises `ValueError`.
4. **Header Normalization**:
   - The first non-ignored record is the header row. If there are no non-ignored records, return `[]`.
   - Each header cell is lowercased, runs of non-alphanumeric characters are replaced with a single `_`, and leading/trailing `_` are stripped. If any normalized header is empty, raise `ValueError`.
   - Duplicate normalized headers are disambiguated left-to-right by keeping the first occurrence as-is and appending `_2`, `_3`, etc. to subsequent occurrences (if `col_2` already appeared earlier, skip to the next unused suffix `_k` where `k >= 2`).
5. **Data Rows & Type Coercion**:
   - Every subsequent non-ignored record must have the exact same number of fields as the header row; otherwise raise `ValueError`.
   - **Quoted fields** are ALWAYS kept as `str` (never coerced to `None`, `bool`, or `int`, even if empty or matching a null token).
   - **Unquoted fields** are coerced in this exact priority order:
     1. If the stripped text is in `null_tokens` (exact case-sensitive match), coerce to `None`.
     2. If case-insensitively equal to `"true"` or `"false"`, coerce to `True` or `False`.
     3. If an optional `+`/`-` followed by one or more ASCII digits (`0-9`), and not starting with a leading `'0'` digit after the sign when there is more than one digit (so `"0"`, `"-0"` -> `0`, `"42"` -> `42`, but `"007"`, `"00"`, and `"-01"` stay `str`), coerce to `int`.
     4. Otherwise keep as `str`.

### Example
```python
parse_table('# comment\nItem Name,Count,Item Name\n"007", 10 ,NULL\nWidget,"",true')
# [{'item_name': '007', 'count': 10, 'item_name_2': None},
#  {'item_name': 'Widget', 'count': '', 'item_name_2': True}]
```
