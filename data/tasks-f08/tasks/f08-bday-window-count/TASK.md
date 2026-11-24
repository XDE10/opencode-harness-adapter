Fix `business_day_span(start_date, end_date, holidays=None, weekend=None, inclusive_end=False)` in `solution.py`.

Count business days, holiday hits, and weekend hits in a calendar date span.

## Specification
- `start_date`, `end_date`: strict `"YYYY-MM-DD"` ISO date strings. Raises `ValueError` if invalid or if `start_date > end_date`.
- `holidays`: optional iterable of `"YYYY-MM-DD"` date strings (duplicates are ignored).
- `weekend`: optional iterable of weekday integers `0..6` (`0` = Monday, `6` = Sunday). Defaults to `[5, 6]` when `None`; `[]` means no recurring weekend days. Invalid weekday values raise `ValueError`.
- `inclusive_end`: if `False`, evaluate the half-open span `[start_date, end_date)`; if `True`, evaluate the closed span `[start_date, end_date]`.
- Returns a dictionary with keys `"business_days"`, `"calendar_days"`, `"holiday_hits"`, and `"weekend_hits"`:
  - A day in the span is classified into exactly one bucket in priority order: weekend -> `"weekend_hits"`, else holiday -> `"holiday_hits"`, else `"business_days"`.
  - Thus `business_days + holiday_hits + weekend_hits == calendar_days`.

## Example
`business_day_span("2024-01-01", "2024-01-08", holidays=["2024-01-01"])` -> `{"business_days": 4, "calendar_days": 7, "holiday_hits": 1, "weekend_hits": 2}`.
