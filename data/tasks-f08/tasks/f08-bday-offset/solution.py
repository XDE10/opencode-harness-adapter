from datetime import date, timedelta


def _parse_iso_date(value):
    if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise ValueError(f"invalid ISO date: {value!r}")
    return date.fromisoformat(value)


def _normalize_weekend(weekend):
    raw = weekend or [5, 6]
    days = set()
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 6:
            raise ValueError(f"invalid weekday: {item!r}")
        days.add(item)
    if len(days) == 7:
        raise ValueError("at least one business weekday is required")
    return days


def _normalize_holidays(holidays):
    if holidays is None:
        return set()
    return {_parse_iso_date(item) for item in holidays}


def _is_business_day(day, weekend_days, holiday_days):
    return day.weekday() not in weekend_days and day not in holiday_days


def shift_business_days(start_date, offset, holidays=None, weekend=None, snap="next"):
    """Return the ISO date string shifted by `offset` business days."""
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise ValueError("offset must be an integer")
    if snap not in ("next", "prev", "stay"):
        raise ValueError(f"invalid snap mode: {snap!r}")

    current = _parse_iso_date(start_date)
    weekend_days = _normalize_weekend(weekend)
    holiday_days = _normalize_holidays(holidays)

    if offset == 0:
        return current.isoformat()

    step = timedelta(days=1 if offset > 0 else -1)
    while not _is_business_day(current, weekend_days, holiday_days):
        current += step

    remaining = abs(offset)
    while remaining > 0:
        current += step
        if _is_business_day(current, weekend_days, holiday_days):
            remaining -= 1
    return current.isoformat()
