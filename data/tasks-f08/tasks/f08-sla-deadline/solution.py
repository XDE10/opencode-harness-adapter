from datetime import date, datetime, time, timedelta


def _parse_iso_date(value):
    if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise ValueError(f"invalid ISO date: {value!r}")
    return date.fromisoformat(value)


def _parse_hhmm(value):
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise ValueError(f"invalid HH:MM time: {value!r}")
    return time.fromisoformat(value)


def _parse_timestamp(value):
    if not isinstance(value, str) or len(value) != 16 or value[10] != "T":
        raise ValueError(f"invalid timestamp: {value!r}")
    day = _parse_iso_date(value[:10])
    tod = _parse_hhmm(value[11:])
    return datetime.combine(day, tod)


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


def _next_business_start(day, start_time, weekend_days, holiday_days):
    cur = day
    while cur.weekday() in weekend_days or cur in holiday_days:
        cur += timedelta(days=1)
    return datetime.combine(cur, start_time)


def compute_sla_deadline(created_at, sla_minutes, work_start="09:00", work_end="17:00", holidays=None, weekend=None):
    """Compute the SLA completion timestamp within business working hours."""
    if isinstance(sla_minutes, bool) or not isinstance(sla_minutes, int) or sla_minutes < 0:
        raise ValueError("sla_minutes must be a non-negative integer")

    cursor = _parse_timestamp(created_at)
    start_t = _parse_hhmm(work_start)
    end_t = _parse_hhmm(work_end)
    if start_t >= end_t:
        raise ValueError("work_start must be earlier than work_end")

    weekend_days = _normalize_weekend(weekend)
    holiday_days = set() if holidays is None else {_parse_iso_date(item) for item in holidays}

    if sla_minutes == 0:
        return cursor.strftime("%Y-%m-%dT%H:%M")

    cur_day = cursor.date()
    if cur_day.weekday() in weekend_days or cur_day in holiday_days:
        cursor = _next_business_start(cur_day, start_t, weekend_days, holiday_days)
    elif cursor.time() < start_t:
        cursor = datetime.combine(cur_day, start_t)
    elif cursor.time() >= end_t:
        cursor = _next_business_start(cur_day + timedelta(days=1), start_t, weekend_days, holiday_days)

    remaining = sla_minutes
    while remaining > 0:
        day_end = datetime.combine(cursor.date(), end_t)
        avail = int((day_end - cursor).total_seconds() // 60)
        if remaining < avail:
            cursor += timedelta(minutes=remaining)
            remaining = 0
        else:
            remaining -= avail
            cursor = _next_business_start(cursor.date() + timedelta(days=1), start_t, weekend_days, holiday_days)
    return cursor.strftime("%Y-%m-%dT%H:%M")
