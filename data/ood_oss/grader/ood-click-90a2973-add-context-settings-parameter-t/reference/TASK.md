# Issue in `click`: Add `context_settings` parameter to `CliRunner.invoke`

This repository snapshot comes from `click` (license: BSD-3-Clause).

## Problem Summary
Add `context_settings` parameter to `CliRunner.invoke`

Closes #2110

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `src/click/testing.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
FAILED _oca_hidden_tests/test_termui.py::test_prompt_and_confirm_ansi_respects_color[context-no-color-prompt]
FAILED _oca_hidden_tests/test_testing.py::test_context_settings_color[False-None-None-False]
FAILED _oca_hidden_tests/test_testing.py::test_context_settings_color[True-None-None-True]
FAILED _oca_hidden_tests/test_testing.py::test_context_settings_color[False-context_settings2-None-False]
FAILED _oca_hidden_tests/test_testing.py::test_context_settings_color[True-context_settings3-None-True]
FAILED _oca_hidden_tests/test_testing.py::test_context_settings_color[False-context_settings4-None-False]
FAILED _oca_hidden_tests/test_testing.py::test_context_settings_color[True-context_setting
```
