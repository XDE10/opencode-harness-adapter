# Issue Report: `r13s2cron` Cron & Resource Conflict Planner

## Context
`r13s2cron` parses 4-field day-bounded cron expressions (`minute hour day_of_month month`), evaluates candidate dispatch times against calendar blackout windows, and plans resource-exclusive job executions with transactional overrides and rollback support.

## Symptom Summary
During staging acceptance tests for multi-tenant maintenance scheduling, two issues surfaced:
1. **Stepped range cron expressions (`A-B/S`) and boundary blackout evaluations**:
   - Step expressions over a range like `10-30/10` or `1-5/2` are generating values starting from the field's global minimum (`min_val`) or up to the global maximum (`max_val`) instead of staying strictly within the specified `A..B` range starting at `A`.
   - Blackout windows (`BlackoutWindow(start, end)`) are documented as half-open intervals `[start, end)`—a timestamp equal to `start` is blocked, while a timestamp equal to `end` is allowed immediately as the blackout ends. Currently, boundary checks on `BlackoutWindow.contains` are inconsistent at the `end` boundary.
2. **Resource conflict resolution & snapshot rollback in `SchedulePlanner`**:
   - When multiple jobs compete for the same `resource_key` at the exact same firing timestamp `dt`, `plan_window` must arbitrate deterministically: highest `priority` wins, with ties broken by lexicographically smallest `job_id`. Currently, tie-breaking or lower-priority eviction fails when jobs are registered in certain orders.
   - `SchedulePlanner.checkpoint()` / `rollback(token)` is supposed to restore both registered jobs **and** blackout windows to their exact state at checkpoint creation time, without mutating snapshots across subsequent registrations. Currently, blackouts added after a checkpoint leak through after `rollback()`, and rolled-back job maps remain coupled to live mutations.

## Behavioral Specification

### 1. Cron Expression Parsing (`r13s2cron.cron`)
- Format: `"<minute> <hour> <day> <month>"` (4 whitespace-separated fields).
  - `minute`: `0..59`
  - `hour`: `0..23`
  - `day`: `1..31`
  - `month`: `1..12`
- Supported tokens per comma-separated part in a field:
  - `*`: all valid integers `min_val..max_val`.
  - `*/step`: integers from `min_val` to `max_val` inclusive with stride `step` (`min_val, min_val + step, ...`).
  - `start-end`: all integers from `start` to `end` inclusive.
  - `start-end/step`: integers starting at `start` up to `end` inclusive with stride `step` (`start, start + step, ... <= end`).
  - `N`: single integer `N`.
- Validation:
  - Out-of-bounds values, `start > end`, or `step <= 0` must raise `ValueError`.

### 2. Blackout Windows (`r13s2cron.models`)
- `BlackoutWindow(name: str, start: datetime, end: datetime, resources: frozenset[str] | None = None)`:
  - Represents a half-open interval `[start, end)`.
  - `window.blocks(dt, resource_key)` returns `True` iff `start <= dt < end` and (`resources is None` or `resource_key in resources`).

### 3. Conflict Resolution & Transactional Rollback (`r13s2cron.planner`)
- `SchedulePlanner.plan_window(start: datetime, end: datetime) -> list[PlannedRun]`:
  - Scans minute-by-minute from `start` to `end` inclusive (seconds/microseconds normalized to 0).
  - For each minute `dt`, finds all registered jobs whose cron spec matches `dt` and that are **not** blocked by any registered `BlackoutWindow` for `job.resource_key`.
  - If multiple matching, unblocked jobs share the same `resource_key` at `dt`, only **one** winner is scheduled:
    1. Highest `job.priority` (integer, larger means higher priority).
    2. If tied on `priority`, lexicographically smallest `job.job_id` (`"job-a" < "job-b"`).
  - Across different `resource_key`s at the same timestamp `dt`, runs are ordered in the returned list by `(dt, resource_key, job_id)`.
- `checkpoint() -> int` and `rollback(token: int) -> None`:
  - `checkpoint()` captures an isolated snapshot of both registered jobs and blackout windows and returns an integer token.
  - `rollback(token)` restores both jobs and blackouts to the snapshot state. Subsequent mutations after `rollback(token)` must not corrupt the stored checkpoint if `rollback(token)` is called again.
  - Calling `rollback` with an unknown token raises `KeyError`.
