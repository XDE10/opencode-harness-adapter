# Issue in `packaging`: feat: expose syntax error details on InvalidRequirement and InvalidMarker (#1547)

This repository snapshot comes from `packaging` (license: Apache-2.0 OR BSD-2-Clause).

## Problem Summary
feat: expose syntax error details on InvalidRequirement and InvalidMarker (#1547)

Add message, source, and span attributes, copied from the internal
ParserSyntaxError. Users no longer need to import it from a private
module and inspect __cause__.

Assisted-by: ClaudeCode:claude-opus-5-5

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `src/packaging/markers.py`
- `src/packaging/requirements.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E   AttributeError: 'InvalidRequirement' object has no attribute 'message'
FAILED _oca_hidden_tests/test_markers.py::TestMarker::test_invalid_marker_syntax_details
FAILED _oca_hidden_tests/test_markers.py::TestMarker::test_invalid_marker_manual_construction
FAILED _oca_hidden_tests/test_requirements.py::TestRequirementParsing::test_error_syntax_details
FAILED _oca_hidden_tests/test_requirements.py::TestRequirementParsing::test_error_details_absent_for_non_syntax_error
FAILED _oca_hidden_tests/test_requirements.py::TestRequirementParsing::test_error_details_pickle
FAILED _oca_hidden_tests/test_requirements.py::TestRequirementParsing::test_error_manual_construction
```
