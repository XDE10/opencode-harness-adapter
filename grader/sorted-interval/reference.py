from bisect import bisect_left, bisect_right


def range_slice(values, minimum=None, maximum=None,
                include_min=True, include_max=True, reverse=False):
    lower = bisect_left if include_min else bisect_right
    upper = bisect_right if include_max else bisect_left
    start = 0 if minimum is None else lower(values, minimum)
    stop = len(values) if maximum is None else upper(values, maximum)
    selected = values[start:stop]
    return selected[::-1] if reverse else selected
