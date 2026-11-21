def chunked_list(items, size, strict=False):
    if size <= 0:
        raise ValueError("size must be positive")
    if strict and len(items) % size:
        raise ValueError("a final chunk would be incomplete")
    return [items[start:start + size] for start in range(0, len(items), size)]
