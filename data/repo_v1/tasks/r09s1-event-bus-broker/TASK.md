# Issue Report: Multi-Level Wildcard Routing & Dead-Letter Offset Advancement in `r09s1bus`

## Context
`r09s1bus` is an in-memory pub/sub event broker supporting topic wildcard subscriptions, consumer group offset tracking, and dead-letter retry queues.

During staging tests, two problems surfaced:
1. **Multi-level wildcard (`**`) matching at zero segments**: A subscription pattern using `**` (which represents **zero or more** dot-separated topic segments) fails to match topics where `**` corresponds to zero segments (for example, pattern `orders.**.created` fails to match topic `orders.created`, or `orders.**` fails to match `orders`).
2. **Consumer group stall and wrong retry count on dead-letter transition**: When a consumer handler raises an exception repeatedly and reaches `max_retries`, the message is moved to the dead-letter queue (DLQ), but:
   - The consumer group's committed offset does not advance past the dead-lettered event, causing subsequent `poll()` calls to re-process the same failed event endlessly.
   - The dead-letter entry records `attempts` before incrementing for the current failed delivery attempt, and its `next_retry_at` / `dead_lettered_at` metadata is inconsistent with the attempt count.

## Behavioral Specification

### 1. Topic & Pattern Parsing (`r09s1bus.matcher`)
- Topic names and subscription patterns are dot-separated strings of non-empty segments (e.g. `payments.eu.settled`). Leading/trailing dots or empty segments (e.g. `payments..settled` or `""`) must raise `ValueError`.
- Pattern wildcards:
  - `*` matches **exactly one** segment.
  - `**` matches **zero or more** segments (at the start, middle, or end of a pattern).
- `TopicPattern.matches(topic: str) -> bool` returns `True` if the valid topic matches the pattern, or raises `ValueError` if `topic` is malformed.

### 2. Consumer Groups, Retries & Dead-Letter Queue (`r09s1bus.broker`)
- `EventBroker(max_retries: int = 3, retry_backoff: int = 5)` manages published `Event` objects in arrival order (0-indexed log offset).
- `subscribe(group_id: str, pattern: str, handler: Callable[[Event], None])` registers or updates a consumer group subscription.
- `poll(group_id: str, now: int) -> PollResult`:
  - Scans the broker log starting from the group's current committed `offset`.
  - Actually processes at most **one** matching event per `poll()` call.
  - Any non-matching event at the current `offset` immediately advances the group's committed `offset` so the scanner moves forward until it finds a matching event (or reaches the end of the log).
  - When a matching event is found at `offset`:
    - If the event is currently awaiting retry for this group and `now < pending_next_retry_at`, `poll()` does **not** invoke the handler and does **not** advance `offset`; it returns `PollResult(processed=0, dead_lettered=0, next_offset=offset)`.
    - Otherwise, the handler is invoked with the `Event`.
    - **On success**: any pending retry state for `(group_id, event.event_id)` is cleared, the group's committed `offset` advances to `offset + 1`, and `poll()` returns `PollResult(processed=1, dead_lettered=0, next_offset=offset + 1)`.
    - **On exception**: the attempt counter `attempts` for `(group_id, event.event_id)` is incremented by 1 (so the first failure has `attempts == 1`).
      - If `attempts < max_retries`: the event remains at `offset` for retry, with `next_retry_at = now + retry_backoff * attempts`. `poll()` returns `PollResult(processed=0, dead_lettered=0, next_offset=offset)`.
      - If `attempts >= max_retries`: a `DeadLetterRecord(group_id=group_id, event=event, attempts=attempts, last_error=str(exc), failed_at=now)` is appended to the broker's dead-letter queue, pending retry state for `(group_id, event.event_id)` is cleared, the group's committed `offset` advances to `offset + 1`, and `poll()` returns `PollResult(processed=0, dead_lettered=1, next_offset=offset + 1)`.
