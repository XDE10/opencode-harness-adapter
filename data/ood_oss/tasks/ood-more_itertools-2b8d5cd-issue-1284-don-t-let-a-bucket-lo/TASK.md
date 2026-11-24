# Issue in `more_itertools`: Issue 1284: don't let a bucket lookup invent a key

This repository snapshot comes from `more_itertools` (license: MIT).

## Problem Summary
Issue 1284: don't let a bucket lookup invent a key

bucket._cache was a defaultdict(deque), and _get_values opened with
`if self._cache[value]:` — a read that inserts an empty deque on a miss.
__iter__ reports `iter(self._cache)`, so every failed lookup left a
permanent phantom key behind, and __contains__ routes through
_get_values, so a plain `in` test was enough to create one.

The result was that `'c' in s` and `'c' in list(s)` disagreed for the
same object at the same moment, misses accumulated, and the docstring's
own "Get the keys" example returned a fourth key after one membership
test.

Make _cache a plain dict so a lookup cannot insert, and register a key
only where an item with that key is actually seen. A key whose items are
produced straight to the caller is registered at that point, so the
existing test_list case — a key fully consumed through s[key] is still
listed — keeps working.

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `more_itertools/more.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E   AssertionError: Items in the first set but not the second:
E   30
E   AssertionError: Items in the first set but not the second:
E   30
E   AssertionError: Items in the first set but not the second:
E   30
E   AssertionError: Items in the first set but not the second:
E   40
```
