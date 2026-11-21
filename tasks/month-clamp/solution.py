def shift_month(year, month, day, delta):
    offset, target = divmod(month - 1 + delta, 12)
    return [year + offset, target + 1, day]
