def chunked_list(items, size, strict=False):
    return [items[start:start + size] for start in range(0, len(items), size)]
