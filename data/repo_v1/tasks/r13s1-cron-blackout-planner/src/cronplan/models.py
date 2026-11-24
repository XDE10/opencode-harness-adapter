from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class CronSchedule:
    minutes: frozenset[int]
    hours: frozenset[int]
    days_of_month: frozenset[int]
    months: frozenset[int]
    days_of_week: frozenset[int]

    def matches(self, dt: datetime) -> bool:
        cron_dow = dt.weekday()
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and dt.day in self.days_of_month
            and dt.month in self.months
            and cron_dow in self.days_of_week
        )


@dataclass(frozen=True)
class JobSpec:
    job_id: str
    cron_expr: str
    duration_minutes: int = 1
    priority: int = 0

    def __post_init__(self) -> None:
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")


@dataclass(frozen=True)
class BlackoutWindow:
    start: datetime
    end: datetime
    reason: str = "maintenance"

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("BlackoutWindow end must be after start")

    def overlaps_interval(self, run_start: datetime, run_end: datetime) -> bool:
        return self.start <= run_start <= self.end


@dataclass(frozen=True)
class PlannedRun:
    job_id: str
    start: datetime
    end: datetime
    priority: int

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    def overlaps(self, other_start: datetime, other_end: datetime) -> bool:
        return self.start < other_end and other_start < self.end
