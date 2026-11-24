# Issue in `more_itertools`: Issue 1304: make ichunked match chunked for n=0 and negative n

This repository snapshot comes from `more_itertools` (license: MIT).

## Problem Summary
Issue 1304: make ichunked match chunked for n=0 and negative n

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `more_itertools/more.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E   AssertionError: 'n must be at least 0' not found in 'Indices for islice() must be None or an integer: 0 <= x <= sys.maxsize.'
E   ValueError: Stop argument for islice() must be None or an integer: 0 <= x <= sys.maxsize.
FAILED _oca_hidden_tests/test_more.py::IchunkedTests::test_negative - Asserti...
FAILED _oca_hidden_tests/test_more.py::IchunkedTests::test_zero_nonempty - Va...
```
