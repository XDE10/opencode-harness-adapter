from cronplan.models import CronSchedule

FIELD_SPECS: tuple[tuple[str, int, int], ...] = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day_of_month", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 6),
)


def _parse_field(token: str, name: str, min_val: int, max_val: int) -> frozenset[int]:
    values: set[int] = set()
    allow_seven = name == "day_of_week"
    effective_max = 7 if allow_seven else max_val

    for part in token.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"Empty token in {name}")

        step = 1
        if "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if step <= 0:
                raise ValueError(f"Step must be positive in {name}: {part}")
        else:
            base = part

        if base == "*":
            start, end = min_val, max_val
        elif "-" in base:
            s_str, e_str = base.split("-", 1)
            start, end = int(s_str), int(e_str)
            if start < min_val or end > effective_max or start > end:
                raise ValueError(f"Invalid range in {name}: {part}")
        else:
            if "/" in part:
                raise ValueError(f"Step requires range or '*' in {name}: {part}")
            val = int(base)
            if val < min_val or val > effective_max:
                raise ValueError(f"Value out of bounds in {name}: {val}")
            values.add(0 if (allow_seven and val == 7) else val)
            continue

        for v in range(start, end + 1):
            if v % step == 0:
                values.add(0 if (allow_seven and v == 7) else v)

    return frozenset(values)


def parse_cron(expr: str) -> CronSchedule:
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Expected 5 cron fields, got {len(parts)} in '{expr}'")

    parsed = [
        _parse_field(token, name, min_v, max_v)
        for token, (name, min_v, max_v) in zip(parts, FIELD_SPECS)
    ]
    return CronSchedule(
        minutes=parsed[0],
        hours=parsed[1],
        days_of_month=parsed[2],
        months=parsed[3],
        days_of_week=parsed[4],
    )
