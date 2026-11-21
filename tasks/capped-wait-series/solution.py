def wait_schedule(count, initial, cap, budget):
    return [min(cap, initial * 2 ** index) for index in range(count)]
