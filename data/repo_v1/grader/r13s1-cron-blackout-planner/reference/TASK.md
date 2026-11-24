# Issue Report: Cron Blackout & Slot Conflict Planner Discrepancies

## Summary
Our batch orchestrator uses `cronplan` to parse 5-field cron expressions, evaluate blackout maintenance windows, and build conflict-aware execution schedules for stateful jobs. Production incidents have uncovered two issues:
1. Range-with-step cron fields (`start-end/step`, e.g. `10-40/15` or `1-5/2`) and day-of-week matching on Sundays (`0` or `7` in standard cron) are producing inaccurate match sets.
2. When jobs have duration > 1 minute and conflict resolution or blackout windows are active, `SchedulePlanner` miscalculates overlapping execution intervals and blackout overlap boundaries.

## Behavioral Specification

### 1. Cron Expression Parsing (`cronplan.parser`)
`parse_cron(expr: str) -> CronSchedule` parses a standard 5-field cron string:
`minute (0-59)  hour (0-23)  day_of_month (1-31)  month (1-12)  day_of_week (0-6)`
- Supported syntax per field (comma-separated items):
  - `*`: all valid values in `[min_val, max_val]`.
  - `*/step`: values from `min_val` to `max_val` incremented by `step` (`(v - min_val) % step == 0`).
  - `start-end`: inclusive range from `start` to `end`.
  - `start-end/step`: values in the inclusive range `[start, end]` starting at `start` and stepping by `step` (`start, start + step, ... <= end`).
  - Single integer literal `v`.
- **Day-of-week convention (POSIX cron)**:
  - In cron syntax, `0` and `7` both represent **Sunday**, `1` is Monday, ..., `6` is Saturday.
  - Passing `7` as a literal or range endpoint (such as `5-7` or `0,7`) must normalize `7` to `0` (Sunday) and remain valid.
  - Note that Python's `datetime.weekday()` returns `0` for Monday through `6` for Sunday. `CronSchedule.matches(dt)` must match `dt` against the cron `day_of_week` field using the cron convention (`0` = Sunday, `1` = Monday, ..., `6` = Saturday).
- Validation:
  - Must have exactly 5 whitespace-separated fields, otherwise raise `ValueError`.
  - Any step `<= 0`, `start > end` (before `7 -> 0` normalization on `day_of_week`, note `5-7` has `start=5 <= end=7` and spans Friday, Saturday, Sunday `{5, 6, 0}`), or out-of-bounds value must raise `ValueError`.

### 2. Blackout Windows & Job Execution Intervals (`cronplan.models`)
- Every candidate run starting at `start_dt` (truncated/aligned to the minute, `second=0, microsecond=0`) for a `JobSpec` with `duration_minutes` occupies the half-open time interval:
  `[start_dt, start_dt + timedelta(minutes=job.duration_minutes))`
- A `BlackoutWindow(start: datetime, end: datetime, reason: str)` also represents a half-open time interval `[start, end)`.
- A candidate job run overlaps a blackout window if and only if their half-open intervals `[run_start, run_end)` and `[blackout.start, blackout.end)` intersect (`run_start < blackout.end and blackout.start < run_end`).
  - In particular, a job starting before a blackout window whose duration extends *into* the blackout window MUST be blocked by that blackout window.
  - Conversely, a job ending cleanly at `blackout.start` (`run_end == blackout.start`) or starting cleanly at `blackout.end` (`run_start == blackout.end`) does NOT overlap the blackout window.

### 3. Stateful Schedule Planner (`cronplan.planner`)
`SchedulePlanner(max_concurrent: int = 1)` tracks blackout windows, registered jobs, and previously scheduled `PlannedRun` records:
- `plan_horizon(start_dt: datetime, end_dt: datetime) -> list[PlannedRun]`:
  - Scans minute-by-minute from `start_dt` (inclusive) to `end_dt` (inclusive), considering only minutes with `second=0, microsecond=0`. If `start_dt` has non-zero seconds/microseconds, advance to the next whole minute boundary before scanning.
  - At each minute `t`, considers all registered jobs whose cron schedule matches `t`, ordered by:
    1. Higher `priority` first (descending `job.priority`)
    2. Tie-breaker: lexicographical `job.job_id` (ascending)
  - A candidate run `[t, t + duration)` is skipped if:
    - It overlaps any registered `BlackoutWindow`.
    - The same `job_id`already has an active (overlapping) `PlannedRun` in `self.scheduled_runs` whose interval `[existing.start, existing.end)` overlaps `t`.
    - Scheduling it would cause the number of concurrently active runs at any point during `[t, t + duration)` (or at launch time `t` against already scheduled runs overlapping `[t, t + duration)`) to exceed `max_concurrent`. Specifically, count how many already-scheduled runs in `self.scheduled_runs` overlap `[t, t + duration)`; if that count is `>= self.max_concurrent` (or if at any minute within `[t, t + duration)` the active count reaches `max_concurrent`), the candidate cannot be scheduled.
  - Valid runs are appended to `self.scheduled_runs` and returned.
