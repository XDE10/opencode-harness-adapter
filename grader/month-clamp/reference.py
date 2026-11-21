import calendar


def shift_month(year, month, day, delta):
    target_year, month_offset = divmod(year * 12 + month - 1 + delta, 12)
    target_month = month_offset + 1
    limit = calendar.monthrange(target_year, target_month)[1]
    return [target_year, target_month, min(day, limit)]
