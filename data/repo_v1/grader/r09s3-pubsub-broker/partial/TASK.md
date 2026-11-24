# Issue Report: Wildcard Topic Matching & Consumer Group Retry Offset Tracking

## Summary
Our internal pub/sub event broker (`r09s3pkg`) is experiencing two production defects:
1. Multi-level wildcard topic subscriptions (`#`) fail to match certain valid topic hierarchies when `#` appears at the end of a pattern and matches zero trailing segments, or when `#` appears in the middle of a pattern (e.g. `orders.#.created`).
2. When a consumer group fails to process a message and the message is queued for retry or moved to the Dead-Letter Queue (DLQ), the consumer group's committed offset advances prematurely or replays already-acknowledged messages on subsequent polls.

## Behavioral Specification

### 1. Topic Addressing & Wildcard Matcher (`r09s3pkg.matcher`)
- Topic names and subscription patterns are dot-delimited non-empty strings (e.g., `orders.eu.created`).
- Leading, trailing, or consecutive empty segments (such as `.orders`, `orders.`, or `orders..eu`) are invalid in both patterns and topics and must raise `ValueError`.
- Wildcard tokens in subscription patterns:
  - `*` matches **exactly one** segment.
  - `#` matches **zero or more** consecutive segments.
- `compile_pattern(pattern: str) -> TopicPattern` validates the pattern and parses its segments.
- `TopicPattern.matches(topic: str) -> bool` validates `topic` (raising `ValueError` if invalid) and returns `True` if and only if the pattern matches the topic segments according to the `*` and `#` rules above.
  - Examples:
    - `orders.#` matches `orders`, `orders.eu`, and `orders.eu.created`.
    - `orders.#.created` matches `orders.created`, `orders.eu.created`, and `orders.eu.west.created`.
    - `orders.*` matches `orders.eu`, but does **not** match `orders` or `orders.eu.created`.

### 2. Consumer Group Offset Tracker & Dead-Letter Retry Queue (`r09s3pkg.broker`)
- `EventBroker(max_retries: int = 3)` manages published `Event` records in an append-only log with 0-based sequential integer offsets (`0, 1, 2, ...`).
- `publish(topic: str, payload: dict, timestamp: int) -> Event`:
  - Validates the topic (cannot contain `*` or `#`, and must have valid non-empty dot-separated segments) and appends a new `Event` at the next global offset.
- `register_group(group_id: str, pattern: str) -> None`:
  - Registers a consumer group subscribed to `pattern` starting at `committed_offset = 0`.
- `poll_and_process(group_id: str, handler: Callable[[Event], bool], now: int) -> list[Event]`:
  - First processes any due items already in the group's retry queue (`entry.next_retry_at <= now`), ordered by their original `event.offset`.
  - Next scans new events from the broker log starting at the group's scan cursor (`next_offset`) whose `topic` matches the group's `TopicPattern`.
  - For each candidate event (whether from the retry queue or newly scanned from the log), invokes `handler(event)`:
    - If `handler(event)` returns `True`: the event is acknowledged, appended to the returned list of processed events, and removed from the retry queue (if it was a retry).
    - If `handler(event)` returns `False`:
      - The failure count (`attempts`) for that `(group_id, event.offset)` is incremented by 1.
      - If `attempts <= max_retries`, the event remains in (or is added to) the group's retry queue with `next_retry_at = now + (attempts * 10)`.
      - If `attempts > max_retries`, the event is removed from the retry queue and appended to the group's Dead-Letter Queue (`dlq`) as a `DeadLetterEntry(event=event, attempts=attempts, failed_at=now)`.
  - **Cursor & Committed Offset Semantics**:
    - `next_offset` tracks the lowest log offset not yet initially scanned by `group_id`. Once a log event at `offset` has been scanned (even if `handler` returned `False` and queued it for retry), it must **not** be re-scanned from the main log on subsequent `poll_and_process` calls; retries are driven solely by the retry queue.
    - `committed_offset(group_id)` returns the lowest log offset that is still pending for this group—i.e., if the retry queue is non-empty, `committed_offset` is the minimum `event.offset` currently in the retry queue; if the retry queue is empty, `committed_offset` equals `next_offset` (all events up to `next_offset` have either been acknowledged, skipped as non-matching, or terminal-routed to the DLQ).
