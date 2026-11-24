from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class Event:
    offset: int
    topic: str
    payload: dict[str, Any]
    timestamp: int


@dataclass
class DeadLetterEntry:
    group_id: str
    event: Event
    attempts: int
    next_retry_at: int
    last_error: str = ""
    permanently_failed: bool = False


@dataclass
class ConsumerGroup:
    group_id: str
    patterns: list[str]
    handler: Callable[[Event], bool]
    committed_offset: int = 0
    highest_inspected_offset: int = 0
    processed_offsets: set[int] = field(default_factory=set)
