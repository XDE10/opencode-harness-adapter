# Issue in `packaging`: feat: allow set of extras (#1438)

This repository snapshot comes from `packaging` (license: Apache-2.0 OR BSD-2-Clause).

## Problem Summary
feat: allow set of extras (#1438)

* feat(markers): evaluate extra markers against a set of extras

Assisted-by: ClaudeCode:claude-fable-5-1
Assisted-by: ClaudeCode:claude-opus-5-5

ClaudeCode:claude-opus-5-5

* docs: clean up and shorten



* fix(markers): evaluate empty extra set like the empty string

Assisted-by: ClaudeCode:claude-opus-5-5

---------

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `src/packaging/markers.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
FAILED _oca_hidden_tests/test_markers.py::TestExtraSetEvaluation::test_marker_evaluation[tuple-extra == "PDF_Support"-extras11-True]
FAILED _oca_hidden_tests/test_markers.py::TestExtraSetEvaluation::test_marker_evaluation[tuple-extra == "a" and extra == "b"-extras12-True]
FAILED _oca_hidden_tests/test_markers.py::TestExtraSetEvaluation::test_marker_evaluation[tuple-extra == "a" and extra == "b"-extras13-False]
FAILED _oca_hidden_tests/test_markers.py::TestExtraSetEvaluation::test_marker_evaluation[tuple-extra == "a" or extra == "b"-extras14-True]
FAILED _oca_hidden_tests/test_markers.py::TestExtraSetEvaluation::test_undefined_operator[extra ~= "gpu"]
FAILED _oca_hidden_tests/test_markers.py:
```
