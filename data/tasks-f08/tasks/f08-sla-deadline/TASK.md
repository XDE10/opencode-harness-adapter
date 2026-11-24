Fix `compute_sla_deadline(created_at, sla_minutes, work_start="09:00", work_end="17:00", holidays=None, weekend=None)` in `solution.py`.

Compute the SLA completion timestamp `"YYYY-MM-DDTHH:MM"` advancing only during business-day working hours `[work_start, work_end)`.

## Specification
- `created_at`: strict `"YYYY-MM-DDTHH:MM"` timestamp string.
- `sla_minutes`: non-negative integer (`bool` rejected).
- `work_start`, `work_end`: strict `"HH:MM"` (`00:00`..`23:59`) strings with `work_start < work_end`.
- `holidays`: optional iterable of strict `"YYYY-MM-DD"` date strings.
- `weekend`: optional iterable of weekday integers `0..6` (`0` = Monday, `6` = Sunday). Defaults to `[5, 6]` when `None`; `[]` allows all 7 weekdays. At least one weekday must be a non-weekend day.
- Work starts at the earliest moment `>= created_at` that lies inside `[work_start, work_end)` on a business day (note: an arrival at or after `work_end` rolls to `work_start` on the next business day).
- If `sla_minutes == 0`, return that normalized start moment formatted as `"YYYY-MM-DDTHH:MM"`.
- If the remaining SLA minutes exactly consume the rest of the current working day (reaching `work_end`), completion occurs at `work_end` on that same day rather than rolling to the next business day.
- Invalid timestamps, `sla_minutes < 0`, `work_start >= work_end`, invalid `weekend`, or all-7-days-weekend raise `ValueError`.

## Example
`compute_sla_deadline("2024-01-05T16:00", 180, holidays=["2024-01-08"])` -> `"2024-01-09T11:00"`.
