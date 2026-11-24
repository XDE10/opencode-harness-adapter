# Issue in `more_itertools`: Do not yield an empty list for an empty iterable when maxsplit is 0

This repository snapshot comes from `more_itertools` (license: MIT).

## Problem Summary
Do not yield an empty list for an empty iterable when maxsplit is 0

split_before, split_after and split_when share a maxsplit == 0 fast path
that yields list(iterable) unconditionally, so an empty iterable produced
[[]] while every other maxsplit produced []. Their slow paths return
nothing for an empty iterable - split_before and split_after via 'if buf',
split_when via its StopIteration early return - and test_empty_collection
and test_empty_iterable already pin that, but neither passed maxsplit, so
neither reached the fast path.

split_at is left alone: its slow path yields the trailing empty list, which
matches ''.split(',', 0) == [''].

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `more_itertools/more.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E   AssertionError: Lists differ: [[]] != []
E   
E   First list contains 1 additional elements.
E   First extra element 0:
E   []
E   
E   - [[]]
E   + []
```
