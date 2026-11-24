Fix `generate_billing_schedule(anchor_date, count, rule, holidays)` in `solution.py`.

Generate a recurring billing schedule of `count` occurrences with end-of-month clamping, business-day shifting, and ISO-8601 week date reporting.

### Parameters
- `anchor_date`: `"YYYY-MM-DD"` string representing the initial anchor date (occurrence 0). Raise `ValueError` if not a valid calendar date.
- `count`: positive integer (`>= 1`). Raise `ValueError` if `count < 1`.
- `rule`: dict with:
  - `"freq"`: `"MONTHLY"` or `"QUARTERLY"` (every 1 month or every 3 months). Raise `ValueError` for any other frequency.
  - `"interval"`: positive integer (`>= 1`) multiplier for the frequency (`1` month * `interval` for `"MONTHLY"`, `3` months * `interval` for `"QUARTERLY"`). Raise `ValueError` if `interval < 1`.
  - `"roll"`: business-day adjustment policy when a scheduled date falls on a weekend (Saturday/Sunday) or a date in `holidays`:
    - `"FOLLOWING"`: shift forward to the next business day.
    - `"PRECEDING"`: shift backward to the previous business day.
    - `"MODIFIED_FOLLOWING"`: shift forward to the next business day, **unless** that business day falls in a different calendar month than the unadjusted scheduled date, in which case shift backward to the previous business day.
    Raise `ValueError` for any other `"roll"` value.
- `holidays`: list of `"YYYY-MM-DD"` strings.

### Recurrence & End-of-Month Clamping Rules
1. Occurrence `k` (`0 <= k < count`) is computed by adding `k * step_months` directly to the **original `anchor_date`'s year and month** (never chain from the previous occurrence's clamped or rolled date!).
2. The target day-of-month for every occurrence is always `anchor_date.day`, clamped to the maximum valid day of the target `(year, month)` (e.g. an anchor on `2024-01-31` produces unadjusted dates `2024-01-31`, `2024-02-29`, `2024-03-31`, `2024-04-30`, ...).
3. Each unadjusted scheduled date is then independently adjusted according to `rule["roll"]` and `holidays`.
4. Note that occurrence `k = 0` (`anchor_date` itself) is also subject to business-day adjustment if `anchor_date` falls on a weekend or holiday.

### Output Format
Return a list of `count` dicts in occurrence order (`k = 0` to `count - 1`):
```python
{
    "index": k,                      # 0-based int
    "scheduled_date": "YYYY-MM-DD",  # unadjusted clamped date
    "effective_date": "YYYY-MM-DD",  # business-day adjusted date
    "shifted_days": int,             # (effective_date - scheduled_date).days (signed int, e.g. -1 or +2)
    "iso_week": "YYYY-Www-D"         # ISO-8601 week date of effective_date, e.g. "2026-W01-4"
}
```
In `"iso_week"`, `YYYY` is the 4-digit **ISO week-numbering year** (which can differ from `effective_date.year` around Jan 1 / Dec 31), `ww` is the zero-padded 2-digit ISO week number (`01`–`53`), and `D` is the ISO weekday (`1` = Monday through `7` = Sunday).

### Example
```python
generate_billing_schedule(
    "2025-01-31", 3,
    {"freq": "MONTHLY", "interval": 1, "roll": "MODIFIED_FOLLOWING"},
    ["2025-02-28"]
)
# k=0: scheduled 2025-01-31 (Fri) -> effective 2025-01-31, shifted 0, iso_week "2025-W05-5"
# k=1: scheduled 2025-02-28 (Fri, holiday) -> next bus day is Mar 3 (diff month!), so rolls back to 2025-02-27 (Thu), shifted -1, iso_week "2025-W09-4"
# k=2: scheduled 2025-03-31 (Mon) -> effective 2025-03-31, shifted 0, iso_week "2025-W14-1"
```
