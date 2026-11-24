# Issue in `more_itertools`: fix: honour a falsey key in all_unique

This repository snapshot comes from `more_itertools` (license: MIT).

## Problem Summary
fix: honour a falsey key in all_unique

all_unique applied the key with `map(key, iterable) if key else iterable`, so a falsey callable was silently ignored. it now checks `key is not None` like the other key functions, same fix as #1309.

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `more_itertools/more.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E   AssertionError: True != False
FAILED _oca_hidden_tests/test_more.py::AllUniqueTests::test_falsey_key_is_honoured
```
