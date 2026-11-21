def range_slice(values, minimum=None, maximum=None,
                include_min=True, include_max=True, reverse=False):
    return [item for item in values
            if (minimum is None or item > minimum or (include_min and item == minimum))
            and (maximum is None or item < maximum or (include_max and item == maximum))]
