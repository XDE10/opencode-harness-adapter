from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


def parse_field(token: str, min_val: int, max_val: int) -> frozenset[int]:
    if not token:
        raise ValueError("Empty cron field token")
    values: set[int] = set()
    for part in token.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"Invalid empty part in '{token}'")
        step = 1
        if "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"Step must be positive in '{part}'")
        else:
            base = part

        if base == "*":
            start, end = min_val, max_val
        elif "-" in base:
            s_str, e_str = base.split("-", 1)
            start, end = int(s_str), int(e_str)
            if start < min_val or end > max_val or start > end:
                raise ValueError(f"Range out of bounds in '{part}'")
        else:
            val = int(base)
            if val < min_val or val > max_val:
                raise ValueError(f"Value out of bounds in '{part}'")
            if "/" in part:
                start, end = val, max_val
            else:
                values.add(val)
                continue

        values.update(range(start, end + 1, step))

    return frozenset(values)


@dataclass(frozen=True)
class CronSpec:
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self.minutes
            and dt.hour in self.hours
            and dt.day in self.days
            and dt.month in self.months
        )


def parse_cron(expr: str) -> CronSpec:
    parts = expr.strip().split()
    if len(parts) != 4:
        raise ValueError(f"Expected 4 cron fields (min hour day month), got {len(parts)}")
    return CronSpec(
        minutes=parse_field(parts[0], 0, 59),
        hours=parse_field(parts[1], 0, 23),
        days=parse_field(parts[2], 1, 31),
        months=parse_field(parts[3], 1, 12),
    )
