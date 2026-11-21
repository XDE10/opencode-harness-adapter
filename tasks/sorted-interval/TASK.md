Fix `range_slice(values, minimum=None, maximum=None,
include_min=True, include_max=True, reverse=False)` in `solution.py`.
Values is a sorted list of integers and can contain duplicates. Return
only the values within the optional bounds, respecting each inclusive
flag independently and retaining duplicates. None is an unbounded side.
Return results in ascending order, or descending when reverse is true.
An empty or reversed interval returns an empty list.
