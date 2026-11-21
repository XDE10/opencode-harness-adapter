def minutes_until(now, target, include_now=False):
    wait = (target - now) % 1440
    if wait == 0 and not include_now:
        return 1440
    return wait
