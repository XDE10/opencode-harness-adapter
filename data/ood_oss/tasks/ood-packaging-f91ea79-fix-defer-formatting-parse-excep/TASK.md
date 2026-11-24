# Issue in `packaging`: fix: defer formatting parse exception messages (#1554)

This repository snapshot comes from `packaging` (license: Apache-2.0 OR BSD-2-Clause).

## Problem Summary
fix: defer formatting parse exception messages (#1554)

* fix: defer formatting parse exception messages

Preserve ValueError construction for subclasses and arguments that cannot be formatted during initialization. Compute the fallback message on first access while keeping the parser-supplied diagnostics.

Assisted-by: OpenAI Codex

* Match functools import style in requirements

---------

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `src/packaging/markers.py`
- `src/packaging/requirements.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E   AttributeError: 'LocatedError' object has no attribute 'filename'
FAILED _oca_hidden_tests/test_markers.py::TestMarker::test_invalid_marker_defers_argument_formatting
FAILED _oca_hidden_tests/test_requirements.py::TestRequirementParsing::test_error_subclass_can_initialize_context
```
