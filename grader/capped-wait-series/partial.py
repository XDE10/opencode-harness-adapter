def wait_schedule(count, initial, cap, budget):
    waits = []
    for index in range(count):
        if not budget:
            break
        wait = min(cap, initial * 2 ** index)
        if wait > budget:
            break
        waits.append(wait)
        budget -= wait
    return waits
