# Issue in `packaging`: fix(requirements): parse === followed by a spaced specifier (#1531)

This repository snapshot comes from `packaging` (license: Apache-2.0 OR BSD-2-Clause).

## Problem Summary
fix(requirements): parse === followed by a spaced specifier (#1531)

The SpecifierSet fast path skipped any specifier list containing ===, so
the token loop parsed it and the === token took the comma and the next
operator. SpecifierSet splits on commas in both paths, so the exclusion
is not needed.

Fixes #1500

Assisted-by: ClaudeCode:claude-fable-5-2

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `src/packaging/_parser.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E   packaging.requirements.InvalidRequirement: Expected comma (within version specifier), semicolon (after version specifier) or end
E       foo===arbitrarystring,>= 1 ; python_version >= '3'
E          ~~~~~~~~~~~~~~~~~~~~~~^
FAILED _oca_hidden_tests/test_requirements.py::TestRequirementParsing::test_nonempty_arbitrary_version[===arbitrarystring,>= 1]
FAILED _oca_hidden_tests/test_requirements.py::TestRequirementParsing::test_nonempty_arbitrary_version[===arbitrarystring, >=1]
FAILED _oca_hidden_tests/test_requirements.py::TestRequirementParsing::test_nonempty_arbitrary_version[ (===arbitrarystring,>= 1)]
FAILED _oca_hidden_tests/test_requirements.py::TestRequirementParsing::test_nonempty_a
```
