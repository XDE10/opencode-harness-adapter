# Issue Report: Wildcard Topic Matching & Dead-Letter Offset Rollback in `r09s2bus`

## Summary
We found two operational defects in `r09s2bus`, our in-memory pub/sub broker with topic wildcard routing, consumer-group offset checkpoints, and dead-letter retry scheduling:

1. **Multi-level wildcard (`#`) topic matching misses zero-segment matches and mid-pattern multi-segment expansions**:
   - Topic strings and subscription patterns are dot-separated segment lists (e.g. `orders.eu.created`).
   - `+` matches exactly **one** non-empty segment.
   - `#` matches **zero or more** segments anywhere it appears in a pattern:
     - Trailing `#`: pattern `orders.#` must match `orders`, `orders.eu`, and `orders.eu.created`.
     - Mid-pattern `#`: pattern `orders.#.failed` must match `orders.failed` (zero segments for `#`), `orders.eu.failed` (one segment), and `orders.eu.west.failed` (multiple segments).
   - Currently, `topic_matches` fails when `#` corresponds to zero segments or when `#` precedes trailing literal/wildcard segments.

2. **Consumer group offset rollback & DLQ replay on handler failure**:
   - `EventBroker.poll_group(group_id, now)` fetches all events with `offset > committed_offset` in ascending offset order.
   - Non-matching events advance the group's `committed_offset` (so long as no earlier event is currently blocked in the DLQ).
   - For each matching event:
     - If the group's handler returns `True`, the group's `committed_offset` advances to `event.offset`.
     - If the group's handler returns `False` (or raises an exception), delivery for that group **stops immediately** at the failing event (subsequent queued events in the same poll batch must not be processed or committed).
     - The failing event must be recorded in the Dead-Letter Queue (`DeadLetterEntry`) with `attempts` incremented and `next_retry_at = now + backoff_seconds * attempts`, **and** the group's `committed_offset` must remain at the last contiguous successfully processed offset prior to the failed event.
   - Furthermore, when `EventBroker.retry_dead_letters(group_id, now)` runs for due entries (`entry.next_retry_at <= now` and not `entry.permanently_failed`):
     - If the handler succeeds on retry, the entry is removed from the DLQ. If `entry.event.offset == group.committed_offset + 1` (or there are no remaining DLQ entries with a lower offset than the highest contiguous processed offset), `committed_offset` must advance to reflect all contiguous succeeded offsets (and any previously blocked events after the failed event remain eligible for subsequent `poll_group` calls).
     - Specifically, `poll_group` must not permanently skip events or advance `committed_offset` past an event that entered the DLQ, and `rollback_to(group_id, target_offset)` must reset `committed_offset` to `target_offset` and purge any DLQ entries for `group_id` whose `event.offset > target_offset` so those events will be cleanly re-polled from the log.

## Behavioral Specification
- `topic_matches(pattern: str, topic: str) -> bool`:
  - Empty pattern or empty topic returns `False`.
  - Segments are split on `.`.
  - `+` matches any single segment; `#` matches 0 or more consecutive segments.
- `ConsumerGroup`:
  - Tracks `group_id`, `patterns`, `handler`, `committed_offset` (starts at `0`), and `processed_offsets: set[int]`.
- `EventBroker`:
  - `publish(topic: str, payload: dict, timestamp: int) -> Event`: assigns 1-based monotonically increasing `offset`.
  - `poll_group(group_id: str, now: int) -> list[Event]`: inspects events with `offset > committed_offset` in offset order. Stops on the first failure (or existing DLQ entry) in the batch, enqueues/updates the failed event in the DLQ, and only advances `committed_offset` across contiguous succeeded/non-matching events. Returns the list of matching events that succeeded during this `poll_group` call.
  - `retry_dead_letters(group_id: str, now: int) -> list[Event]`: retries due DLQ entries for `group_id` in ascending `event.offset` order.
    - If a retry fails at `attempts == max_retries`, `entry.permanently_failed` becomes `True` and it is no longer retried.
    - If retry succeeds, removes the DLQ entry, marks `event.offset` as processed, and advances `committed_offset` across any contiguous processed/non-matching offsets up to the highest contiguous offset inspected by the group.
  - `rollback_to(group_id: str, target_offset: int) -> None`: sets `committed_offset = target_offset`, removes all `offset > target_offset` from `processed_offsets`, and removes all DLQ entries for `group_id` where `entry.event.offset > target_offset`.
