def last_index(items, needle, start=0, stop=None):
    first, end, _ = slice(start, stop).indices(len(items))
    for index in range(end - 1, first - 1, -1):
        if items[index] == needle:
            return index
    return -1
