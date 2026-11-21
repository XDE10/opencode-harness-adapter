def wait_schedule(count, initial, cap, budget):
    waits = []
    wait = min(cap, initial)
    for _ in range(count):
        if budget == 0:
            break
        delay = min(wait, budget)
        waits.append(delay)
        budget -= delay
        wait = min(cap, 2 * wait)
    return waits
