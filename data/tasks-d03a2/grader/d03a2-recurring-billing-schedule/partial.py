import calendar
from datetime import date, timedelta


def _parse_date(s):
    parts = s.split("-")
    if len(parts) != 3:
        raise ValueError("Invalid date format")
    return date(int(parts[0]), int(parts[1]), int(parts[2]))


def _is_business_day(d, holiday_set):
    return d.weekday() < 5 and d.isoformat() not in holiday_set


def _shift_following(d, holiday_set):
    cur = d
    while not _is_business_day(cur, holiday_set):
        cur += timedelta(days=1)
    return cur


def _shift_preceding(d, holiday_set):
    cur = d
    while not _is_business_day(cur, holiday_set):
        cur -= timedelta(days=1)
    return cur


def _apply_roll(d, roll, holiday_set):
    if roll == "FOLLOWING":
        return _shift_following(d, holiday_set)
    if roll == "PRECEDING":
        return _shift_preceding(d, holiday_set)
    if roll == "MODIFIED_FOLLOWING":
        fwd = _shift_following(d, holiday_set)
        if fwd.month != d.month:
            return _shift_preceding(d, holiday_set)
        return fwd
    raise ValueError(f"Unknown roll policy: {roll}")


def _add_months_clamped(y, m, anchor_day, offset_months):
    total_m = (y * 12 + (m - 1)) + offset_months
    ny, nm = divmod(total_m, 12)
    nm += 1
    max_day = calendar.monthrange(ny, nm)[1]
    return date(ny, nm, min(anchor_day, max_day))


def _format_iso_week(d):
    iso = d.isocalendar()
    return f"{d.year:04d}-W{iso[1]:02d}-{iso[2]}"


def generate_billing_schedule(anchor_date, count, rule, holidays):
    if count < 1:
        raise ValueError("count must be >= 1")
    anchor = _parse_date(anchor_date)
    freq = rule.get("freq")
    if freq == "MONTHLY":
        base_step = 1
    elif freq == "QUARTERLY":
        base_step = 3
    else:
        raise ValueError("Invalid freq")

    interval = rule.get("interval", 1)
    if not isinstance(interval, int) or interval < 1:
        raise ValueError("interval must be >= 1")

    roll = rule.get("roll")
    if roll not in ("FOLLOWING", "PRECEDING", "MODIFIED_FOLLOWING"):
        raise ValueError("Invalid roll")

    holiday_set = set(holidays)
    step_months = base_step * interval
    schedule = []

    for k in range(count):
        sched = _add_months_clamped(anchor.year, anchor.month, anchor.day, k * step_months)
        eff = _apply_roll(sched, roll, holiday_set)
        shifted = (eff - sched).days
        schedule.append({
            "index": k,
            "scheduled_date": sched.isoformat(),
            "effective_date": eff.isoformat(),
            "shifted_days": shifted,
            "iso_week": _format_iso_week(eff),
        })

    return schedule
