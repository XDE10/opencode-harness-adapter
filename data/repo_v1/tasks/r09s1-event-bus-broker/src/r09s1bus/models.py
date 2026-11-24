from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class Event:
    event_id: str
    topic: str
    payload: Dict[str, Any]
    published_at: int


@dataclass(frozen=True)
class DeadLetterRecord:
    group_id: str
    event: Event
    attempts: int
    last_error: str
    failed_at: int


@dataclass(frozen=True)
class PollResult:
    processed: int
    dead_lettered: int
    next_offset: int


@dataclass
class RetryState:
    attempts: int = 0
    next_retry_at: int = 0
    last_error: str = ""
