from dataclasses import dataclass, field
from typing import Any, Callable

from r09s3pkg.matcher import TopicPattern, compile_pattern, split_topic_segments
from r09s3pkg.models import DeadLetterEntry, Event, RetryEntry


@dataclass
class _ConsumerGroupState:
    group_id: str
    pattern: TopicPattern
    next_offset: int = 0
    retries: dict[int, RetryEntry] = field(default_factory=dict)
    dlq: list[DeadLetterEntry] = field(default_factory=list)


class EventBroker:
    def __init__(self, max_retries: int = 3) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.max_retries = max_retries
        self._log: list[Event] = []
        self._groups: dict[str, _ConsumerGroupState] = {}

    def publish(self, topic: str, payload: dict[str, Any], timestamp: int) -> Event:
        split_topic_segments(topic, allow_wildcards=False)
        event = Event(
            offset=len(self._log),
            topic=topic,
            payload=dict(payload),
            timestamp=timestamp,
        )
        self._log.append(event)
        return event

    def register_group(self, group_id: str, pattern: str) -> None:
        if not group_id:
            raise ValueError("group_id must be non-empty")
        compiled = compile_pattern(pattern)
        self._groups[group_id] = _ConsumerGroupState(
            group_id=group_id,
            pattern=compiled,
        )

    def _get_group(self, group_id: str) -> _ConsumerGroupState:
        if group_id not in self._groups:
            raise KeyError(f"Unknown consumer group '{group_id}'")
        return self._groups[group_id]

    def poll_and_process(
        self,
        group_id: str,
        handler: Callable[[Event], bool],
        now: int,
    ) -> list[Event]:
        state = self._get_group(group_id)
        acknowledged: list[Event] = []

        due_offsets = sorted(
            offset
            for offset, entry in state.retries.items()
            if entry.next_retry_at <= now
        )
        for offset in due_offsets:
            entry = state.retries[offset]
            if handler(entry.event):
                acknowledged.append(entry.event)
                del state.retries[offset]
            else:
                self._record_failure(state, entry.event, entry.attempts + 1, now)

        start_offset = state.next_offset
        for idx in range(start_offset, len(self._log)):
            event = self._log[idx]
            state.next_offset = idx + 1
            if not state.pattern.matches(event.topic):
                continue

            if handler(event):
                acknowledged.append(event)
            else:
                self._record_failure(state, event, 1, now)

        return acknowledged

    def _record_failure(
        self,
        state: _ConsumerGroupState,
        event: Event,
        attempts: int,
        now: int,
    ) -> None:
        if attempts <= self.max_retries:
            state.retries[event.offset] = RetryEntry(
                event=event,
                attempts=attempts,
                next_retry_at=now + (attempts * 10),
            )
        else:
            state.retries.pop(event.offset, None)
            state.dlq.append(
                DeadLetterEntry(
                    event=event,
                    attempts=attempts,
                    failed_at=now,
                )
            )

    def committed_offset(self, group_id: str) -> int:
        state = self._get_group(group_id)
        if state.retries:
            return min(state.retries.keys())
        return state.next_offset

    def pending_retries(self, group_id: str) -> list[RetryEntry]:
        state = self._get_group(group_id)
        return [state.retries[k] for k in sorted(state.retries)]

    def dead_letters(self, group_id: str) -> list[DeadLetterEntry]:
        state = self._get_group(group_id)
        return list(state.dlq)
