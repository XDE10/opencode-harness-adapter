from datetime import date, timedelta


def _parse_iso_date(value):
    if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise ValueError(f"invalid ISO date: {value!r}")
    return date.fromisoformat(value)


def _normalize_weekend(weekend):
    raw = [5, 6] if weekend is None else weekend
    days = set()
    for item in raw:
        if isinstance(item, bool) or not isinstance(item, int) or not 0 <= item <= 6:
            raise ValueError(f"invalid weekday: {item!r}")
        days.add(item)
    return days


def _normalize_holidays(holidays):
    if holidays is None:
        return set()
    return {_parse_iso_date(item) for item in holidays}


def business_day_span(start_date, end_date, holidays=None, weekend=None, inclusive_end=False):
    """Count business, holiday, and weekend days in `[start_date, end_date)` or `[start_date, end_date]`."""
    if not isinstance(inclusive_end, bool):
        raise ValueError("inclusive_end must be a bool")

    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    if start > end:
        raise ValueError("start_date must not exceed end_date")

    weekend_days = _normalize_weekend(weekend)
    holiday_days = _normalize_holidays(holidays)

    stop = end + timedelta(days=1) if inclusive_end else end
    calendar_days = 0
    weekend_hits = 0
    holiday_hits = 0
    business_days = 0
    current = start

    while current < stop:
        calendar_days += 1
        if current.weekday() in weekend_days:
            weekend_hits += 1
        elif current in holiday_days:
            holiday_hits += 1
        else:
            business_days += 1
        current += timedelta(days=1)

    return {
        "business_days": business_days,
        "calendar_days": calendar_days,
        "holiday_hits": holiday_hits,
        "weekend_hits": weekend_hits,
    }
