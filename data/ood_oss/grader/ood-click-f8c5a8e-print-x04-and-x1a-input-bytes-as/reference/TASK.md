# Issue in `click`: Print `\x04` and `\x1a` input bytes as `^D` and `^Z` in `CliRunner`

This repository snapshot comes from `click` (license: BSD-3-Clause).

## Problem Summary
Print `\x04` and `\x1a` input bytes as `^D` and `^Z` in `CliRunner`

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `src/click/testing.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E       baz
E     + 3
E     - ^D
E     - 2
E   AssertionError: assert 'bar\nbaz\n\x043\n' == 'bar\nbaz\n^D\n2\n'
E       bar
E       baz
E     + 3
```
