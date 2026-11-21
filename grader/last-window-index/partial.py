def last_index(items, needle, start=0, stop=None):
    window = items[start:stop]
    for offset in range(len(window) - 1, -1, -1):
        if window[offset] == needle:
            return start + offset
    return -1
