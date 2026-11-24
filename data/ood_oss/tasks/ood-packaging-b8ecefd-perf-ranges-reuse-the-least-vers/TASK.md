# Issue in `packaging`: perf(ranges): reuse the least version above a boundary (#1563)

This repository snapshot comes from `packaging` (license: Apache-2.0 OR BSD-2-Clause).

## Problem Summary
perf(ranges): reuse the least version above a boundary (#1563)

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `src/packaging/_ranges.py`
- `src/packaging/ranges.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E   AttributeError: 'BoundaryVersion' object has no attribute 'successor'
FAILED _oca_hidden_tests/test_ranges.py::TestBoundaryCanonicalization::test_boundary_reuses_its_successor
```
