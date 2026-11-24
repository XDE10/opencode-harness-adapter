# Issue in `click`: Fix short help abbreviation

This repository snapshot comes from `click` (license: BSD-3-Clause).

## Problem Summary
Fix short help abbreviation

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `src/click/utils.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E   AssertionError: assert 'Weigh apples vs.' == 'Weigh apples vs....'
E     - Weigh apples vs....
E     ?                 ---
E     + Weigh apples vs.
E   AssertionError: assert '123 567 9.' == '123 567...'
E     - 123 567...
E     ?         --
E     + 123 567 9.
```
