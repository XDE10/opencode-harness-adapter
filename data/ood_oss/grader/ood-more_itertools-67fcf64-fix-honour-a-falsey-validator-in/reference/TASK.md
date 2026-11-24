# Issue in `more_itertools`: fix: honour a falsey validator in bucket (#1308)

This repository snapshot comes from `more_itertools` (license: MIT).

## Problem Summary
fix: honour a falsey validator in bucket (#1308)

`bucket` chose its validator with `validator or (lambda x: True)`, so a
falsey but valid callable (e.g. an empty `set` subclass defining
`__call__`) was silently replaced by the default that accepts every key.
Selecting such a bucket then returned items the validator rejected, and
membership tests wrongly reported them present.

Use an `is None` check instead.

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `more_itertools/more.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E   AssertionError: Lists differ: [10] != []
E   
E   First list contains 1 additional elements.
E   First extra element 0:
E   10
E   
E   - [10]
E   + []
```
