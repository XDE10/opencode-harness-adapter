from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    offset: int
    topic: str
    payload: dict[str, Any]
    timestamp: int


@dataclass
class RetryEntry:
    event: Event
    attempts: int
    next_retry_at: int


@dataclass(frozen=True)
class DeadLetterEntry:
    event: Event
    attempts: int
    failed_at: int
