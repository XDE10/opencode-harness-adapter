Fix `shift_business_days(start_date, offset, holidays=None, weekend=None, snap="next")` in `solution.py`.

Shift an ISO date string `"YYYY-MM-DD"` by `offset` business days, skipping weekends and holidays.

## Specification
- `start_date`: strict `"YYYY-MM-DD"` calendar date string.
- `offset`: integer (positive, negative, or `0`; `bool` is rejected).
- `holidays`: optional iterable of strict `"YYYY-MM-DD"` strings treated as non-business days.
- `weekend`: optional iterable of weekday integers `0..6` (`0` = Monday, `6` = Sunday). Defaults to `[5, 6]` when `None`. An empty list `[]` means no recurring weekend days. Raising `ValueError` if all 7 weekdays are marked as weekend or any weekday is outside `0..6`.
- `snap`: controls behavior when `offset == 0` and `start_date` is not a business day:
  - `"next"`: move forward to the next business day.
  - `"prev"`: move backward to the previous business day.
  - `"stay"`: return `start_date` unchanged.
  - Any other value raises `ValueError`.
- When `offset > 0` (`offset < 0`), advance forward (backward) one calendar day at a time until `abs(offset)` business days have been landed on, regardless of whether `start_date` itself is a business day.
- Invalid date strings, `bool` arguments where `int` is expected, invalid `weekend` values, or invalid `snap` values raise `ValueError`.

## Example
`shift_business_days("2024-01-05", 1, holidays=["2024-01-08"])` -> `"2024-01-09"` (Friday Jan 5 skips weekend Jan 6-7 and Monday holiday Jan 8).
