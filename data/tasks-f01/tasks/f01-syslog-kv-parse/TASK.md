Specify and fix `parse_syslog_records(lines, required_fields=None, max_skew_ms=0)` in `solution.py`.

`lines` is a list of raw log strings; blank or whitespace-only lines are ignored.
Each non-blank line consists of whitespace-separated `key=value` tokens:
- Keys must be non-empty and cannot contain `=` or whitespace; duplicate keys in the same line raise `ValueError`.
- Values may be unquoted (non-empty, cannot contain `"` or whitespace) or double-quoted (`"..."`), where `\\` decodes to `\` and `\"` decodes to `"`. Unclosed quotes, trailing characters immediately after a closing quote without whitespace, or missing `=` raise `ValueError`. Empty quoted values (`""`) are valid.
- Every non-blank line must contain `ts`, which must parse as a non-negative base-10 integer (`ValueError` otherwise).
- If `level` is present, normalize it by uppercasing and mapping `WARN` -> `WARNING`, `ERR` -> `ERROR`, and `CRIT` -> `CRITICAL`.
- If `required_fields` is provided, every non-blank line must contain all listed field names (`KeyError` if any are missing).

Validation of syntax, types, and `required_fields` happens before late-arrival filtering.
If `max_skew_ms < 0`, raise `ValueError`. While scanning lines in arrival order, track `max_seen_ts`: a record with `ts < max_seen_ts - max_skew_ms` is dropped as too late (records with `ts == max_seen_ts - max_skew_ms` are kept). Otherwise, accept the record and update `max_seen_ts`.

Return accepted records sorted by `(ts, original_line_index)` where `ts` is an `int` and all other fields are `str`.

Example:
```python
parse_syslog_records(
    ['ts=100 level=warn msg="ok"', 'ts=80 level=info msg="late"', 'ts=95 level=info msg="kept"'],
    max_skew_ms=10,
)
# -> [{"ts": 95, "level": "INFO", "msg": "kept"}, {"ts": 100, "level": "WARNING", "msg": "ok"}]
```
