def shift_month(year, month, day, delta):
    offset, target = divmod(month - 1 + delta, 12)
    month = target + 1
    if month == 2:
        day = min(day, 28)
    elif month in (4, 6, 9, 11):
        day = min(day, 30)
    return [year + offset, month, day]
