from typing import Any, Callable
from r09s2bus.matcher import filter_matching_patterns
from r09s2bus.models import ConsumerGroup, DeadLetterEntry, Event


class EventBroker:
    def __init__(self, max_retries: int = 3, backoff_seconds: int = 10) -> None:
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._events: list[Event] = []
        self._groups: dict[str, ConsumerGroup] = {}
        self._dlq: dict[tuple[str, int], DeadLetterEntry] = {}

    def publish(self, topic: str, payload: dict[str, Any], timestamp: int) -> Event:
        event = Event(
            offset=len(self._events) + 1,
            topic=topic,
            payload=dict(payload),
            timestamp=timestamp,
        )
        self._events.append(event)
        return event

    def register_group(
        self,
        group_id: str,
        patterns: list[str],
        handler: Callable[[Event], bool],
    ) -> ConsumerGroup:
        group = ConsumerGroup(group_id=group_id, patterns=list(patterns), handler=handler)
        self._groups[group_id] = group
        return group

    def get_group(self, group_id: str) -> ConsumerGroup:
        return self._groups[group_id]

    def get_dead_letters(self, group_id: str) -> list[DeadLetterEntry]:
        entries = [e for (gid, _), e in self._dlq.items() if gid == group_id]
        return sorted(entries, key=lambda e: e.event.offset)

    def _matches_group(self, group: ConsumerGroup, event: Event) -> bool:
        return bool(filter_matching_patterns(group.patterns, event.topic))

    def _run_handler(self, group: ConsumerGroup, event: Event) -> tuple[bool, str]:
        try:
            ok = bool(group.handler(event))
            return (ok, "" if ok else "handler_returned_false")
        except Exception as exc:
            return (False, str(exc))

    def _advance_committed_offset(self, group: ConsumerGroup) -> None:
        while (
            group.committed_offset + 1 <= group.highest_inspected_offset
            and (group.committed_offset + 1) in group.processed_offsets
            and (group.group_id, group.committed_offset + 1) not in self._dlq
        ):
            group.committed_offset += 1

    def poll_group(self, group_id: str, now: int) -> list[Event]:
        group = self._groups[group_id]
        delivered: list[Event] = []

        for event in self._events:
            if event.offset <= group.committed_offset:
                continue

            if (group_id, event.offset) in self._dlq:
                break

            if event.offset in group.processed_offsets:
                group.highest_inspected_offset = max(group.highest_inspected_offset, event.offset)
                self._advance_committed_offset(group)
                continue

            if not self._matches_group(group, event):
                group.processed_offsets.add(event.offset)
                group.highest_inspected_offset = max(group.highest_inspected_offset, event.offset)
                self._advance_committed_offset(group)
                continue

            ok, err = self._run_handler(group, event)

            group.highest_inspected_offset = max(group.highest_inspected_offset, event.offset)
            if ok:
                group.processed_offsets.add(event.offset)
                self._advance_committed_offset(group)
                delivered.append(event)
            else:
                self._record_failure(group_id, event, now, err)
                break

        return delivered

    def _record_failure(self, group_id: str, event: Event, now: int, error: str) -> DeadLetterEntry:
        key = (group_id, event.offset)
        existing = self._dlq.get(key)
        attempts = 1 if existing is None else existing.attempts + 1
        permanently_failed = attempts >= self.max_retries
        entry = DeadLetterEntry(
            group_id=group_id,
            event=event,
            attempts=attempts,
            next_retry_at=now + self.backoff_seconds * attempts,
            last_error=error,
            permanently_failed=permanently_failed,
        )
        self._dlq[key] = entry
        return entry

    def retry_dead_letters(self, group_id: str, now: int) -> list[Event]:
        group = self._groups[group_id]
        recovered: list[Event] = []

        for entry in self.get_dead_letters(group_id):
            if entry.permanently_failed or entry.next_retry_at > now:
                continue

            ok, err = self._run_handler(group, entry.event)

            if ok:
                del self._dlq[(group_id, entry.event.offset)]
                group.processed_offsets.add(entry.event.offset)
                self._advance_committed_offset(group)
                recovered.append(entry.event)
            else:
                self._record_failure(group_id, entry.event, now, err)

        return recovered

    def rollback_to(self, group_id: str, target_offset: int) -> None:
        group = self._groups[group_id]
        clamped = max(0, target_offset)
        group.committed_offset = clamped
        group.highest_inspected_offset = clamped
        group.processed_offsets = {
            off for off in group.processed_offsets if off <= clamped
        }
        to_delete = [
            key
            for key, entry in self._dlq.items()
            if key[0] == group_id and entry.event.offset > clamped
        ]
        for key in to_delete:
            del self._dlq[key]
