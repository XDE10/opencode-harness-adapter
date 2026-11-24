from typing import Callable, Dict, List
from r09s1bus.matcher import TopicPattern, validate_topic
from r09s1bus.models import DeadLetterRecord, Event, PollResult, RetryState


class ConsumerGroup:
    def __init__(
        self,
        group_id: str,
        pattern: TopicPattern,
        handler: Callable[[Event], None],
    ) -> None:
        self.group_id = group_id
        self.pattern = pattern
        self.handler = handler
        self.offset: int = 0
        self.retries: Dict[str, RetryState] = {}


class EventBroker:
    def __init__(self, max_retries: int = 3, retry_backoff: int = 5) -> None:
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1")
        if retry_backoff < 0:
            raise ValueError("retry_backoff must be >= 0")
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._events: List[Event] = []
        self._groups: Dict[str, ConsumerGroup] = {}
        self._dlq: List[DeadLetterRecord] = []

    @property
    def dead_letters(self) -> List[DeadLetterRecord]:
        return list(self._dlq)

    def publish(self, event: Event) -> int:
        validate_topic(event.topic, allow_wildcards=False)
        self._events.append(event)
        return len(self._events) - 1

    def subscribe(
        self,
        group_id: str,
        pattern: str,
        handler: Callable[[Event], None],
    ) -> ConsumerGroup:
        compiled = TopicPattern(pattern)
        if group_id in self._groups:
            group = self._groups[group_id]
            group.pattern = compiled
            group.handler = handler
            return group
        group = ConsumerGroup(group_id=group_id, pattern=compiled, handler=handler)
        self._groups[group_id] = group
        return group

    def get_offset(self, group_id: str) -> int:
        return self._groups[group_id].offset

    def poll(self, group_id: str, now: int) -> PollResult:
        if group_id not in self._groups:
            raise KeyError(f"Unknown consumer group: {group_id}")
        group = self._groups[group_id]

        while group.offset < len(self._events):
            event = self._events[group.offset]
            if not group.pattern.matches(event.topic):
                group.offset += 1
                continue

            state = group.retries.get(event.event_id)
            if state is not None and now < state.next_retry_at:
                return PollResult(processed=0, dead_lettered=0, next_offset=group.offset)

            try:
                group.handler(event)
            except Exception as exc:
                if state is None:
                    state = RetryState()
                    group.retries[event.event_id] = state
                state.last_error = str(exc)
                if state.attempts + 1 >= self.max_retries:
                    self._dlq.append(
                        DeadLetterRecord(
                            group_id=group_id,
                            event=event,
                            attempts=state.attempts,
                            last_error=state.last_error,
                            failed_at=now,
                        )
                    )
                    return PollResult(
                        processed=0,
                        dead_lettered=1,
                        next_offset=group.offset,
                    )
                state.attempts += 1
                state.next_retry_at = now + self.retry_backoff * state.attempts
                return PollResult(processed=0, dead_lettered=0, next_offset=group.offset)

            group.retries.pop(event.event_id, None)
            group.offset += 1
            return PollResult(processed=1, dead_lettered=0, next_offset=group.offset)

        return PollResult(processed=0, dead_lettered=0, next_offset=group.offset)
