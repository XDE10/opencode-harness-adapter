# Issue in `packaging`: fix(dependency-groups): report self-inclusion for unnormalized spellings (#1519)

This repository snapshot comes from `packaging` (license: Apache-2.0 OR BSD-2-Clause).

## Problem Summary
fix(dependency-groups): report self-inclusion for unnormalized spellings (#1519)

_validate() normalizes the include name before testing it against the
include stack, but passed the raw item.include_group to
CyclicDependencyGroup. The exception branches on include_group == group
where group is already normalized, so a self-include spelled differently
(e.g. "A" for group "a", or "A_B" for "a.b") fell into the two-node
template and reported a cycle between two names that are one group.

Pass the normalized name so the diagnostic matches the cycle actually
detected.

## Scope
Investigate and fix the bug in the library source modules (relevant area includes:
- `src/packaging/dependency_groups.py`
).
Run `pytest` to verify your changes and avoid regressions.

## Observed Failure Signal (excerpt)
```text
E   assert False
E    +  where False = _group_contains(<ExceptionInfo ExceptionGroup("[dependency-groups] data for 'a-b' was malformed", [CyclicDependencyGroup('Cyclic dependency group include while resolving a-b: A.B -> a-b, a-b -> A.B')]) tblen=7>, CyclicDependencyGroup, match='Cyclic dependency group include while resolving a-b: a-b includes itself')
FAILED _oca_hidden_tests/test_dependency_groups.py::test_cyclic_include_self_with_unnormalized_spelling[group1-Group1-group1]
FAILED _oca_hidden_tests/test_dependency_groups.py::test_cyclic_include_self_with_unnormalized_spelling[group1-GROUP1-group1]
FAILED _oca_hidden_tests/test_dependency_groups.py::test_cyclic_include_self_with_unnormaliz
```
