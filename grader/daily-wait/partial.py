def minutes_until(now, target, include_now=False):
    return (target - now) % 1440
