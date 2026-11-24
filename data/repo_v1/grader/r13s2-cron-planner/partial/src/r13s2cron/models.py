from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class JobDef:
    job_id: str
    cron_expr: str
    resource_key: str
    priority: int = 0


@dataclass(frozen=True)
class BlackoutWindow:
    name: str
    start: datetime
    end: datetime
    resources: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("BlackoutWindow end must be after start")

    def blocks(self, dt: datetime, resource_key: str) -> bool:
        if self.resources is not None and resource_key not in self.resources:
            return False
        return self.start <= dt < self.end


@dataclass(frozen=True)
class PlannedRun:
    job_id: str
    scheduled_at: datetime
    resource_key: str
    priority: int
