# Use the most specific module category

Fix `module_category(module, rules, default='other')` in `solution.py`.

Module and every key in rules are nonempty dotted names made of
nonempty components. A rule matches the exact module or its
descendants at a dot boundary. Pick the longest matching rule
and return its category. Return default if there is no match.
