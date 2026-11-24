Fix `expand_cron_field(field, low, high)` in `solution.py`.

Implement a deterministic cron-field expander.

Inputs:
- `field` must be a `str`; `low` and `high` must be integers with `0 <= low <= high`. Booleans are not accepted as integers. Any violation raises `ValueError`.
- `field` is a comma-separated list of items with no whitespace anywhere. Empty items are invalid. Numeric tokens are non-empty ASCII decimal digit strings; signs are not allowed.

Item forms:
- `N`: the single value `N`.
- `A-B`: every integer from `A` through `B`, inclusive; require `A <= B`.
- `*`: every value from `low` through `high`, inclusive.
- `*/S`: every value from `low` through `high` inclusive, stepping by `S`.
- `A-B/S`: every value from `A` through `B` inclusive, stepping by `S`; require `A <= B`.
- `A/S`: every value from `A` through `high` inclusive, stepping by `S`.

For stepped forms, include the start and each subsequent value while it is `<=` the form's end; the end itself is included when it is reached. `S` must be a positive integer. Every referenced value (`N`, `A`, `B`) must lie in `[low, high]`. More than one `/` in an item, a missing step, or any other malformed syntax raises `ValueError`.

The function returns a list of integers: all produced values with duplicates removed, sorted ascending.

Examples:
`expand_cron_field("2-6,9", 1, 10)` returns `[2, 3, 4, 5, 6, 9]`.
`expand_cron_field("*/20", 0, 40)` returns `[0, 20, 40]`.
