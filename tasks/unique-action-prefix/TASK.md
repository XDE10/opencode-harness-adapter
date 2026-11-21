# Resolve action aliases without choosing ambiguous prefixes

Fix `resolve_action(query, aliases)` in `solution.py`.

Aliases maps nonempty names to canonical action strings. Alias names
are distinct after casefolding. An empty query returns null. Search
case-insensitively using string casefolding. An exact alias takes
precedence. Otherwise, return a canonical action only if all matching
alias prefixes resolve to the same action. Return null for a missing
or ambiguous match. This function only returns a string.
