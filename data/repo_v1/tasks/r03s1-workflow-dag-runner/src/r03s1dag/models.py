from dataclasses import dataclass
from enum import Enum
from typing import Any


class CycleDetectedError(ValueError):
    """Raised when a workflow dependency graph contains a cycle."""


class TaskState(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class TaskNode:
    task_id: str
    action: str
    depends_on: tuple[str, ...] = ()
    retries: int = 0
    allow_partial: bool = False


@dataclass
class LedgerEntry:
    task_id: str
    state: TaskState
    attempts: int
    output: Any = None
    error: str | None = None
