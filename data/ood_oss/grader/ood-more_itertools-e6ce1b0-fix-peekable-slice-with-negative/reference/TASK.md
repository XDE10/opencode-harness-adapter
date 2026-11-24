# Issue in `more_itertools`: Fix peekable slice with negative step and omitted stop unnecessarily caching entire iterable

This repository snapshot comes from `more_itertools` (license: MIT).

## Problem Summary
Fix peekable slice with negative step and omitted stop unnecessarily caching entire iterable

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `more_itertools/more.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E   AssertionError: 100 != 6
FAILED _oca_hidden_tests/test_more.py::PeekableTests::test_slicing_negative_step_omitted_stop
```
