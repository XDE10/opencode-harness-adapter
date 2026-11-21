# Report invalid integer sample positions

Fix `invalid_integer_positions(values, nullable=False)` in `solution.py`.

Return zero-based indexes in input order for values that violate the
integer field type. Only integer values qualify as integers. JSON
booleans are a separate type, as are decimal numbers even if they
have a zero fractional part. When nullable is true, null is also valid.
