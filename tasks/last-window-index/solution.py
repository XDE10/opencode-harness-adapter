def last_index(items, needle, start=0, stop=None):
    for offset, item in enumerate(items[start:stop]):
        if item == needle:
            return offset
    return -1
