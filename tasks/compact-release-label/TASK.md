# Normalize a release display label

Fix `release_label(parts, minimum=2)` in `solution.py`.

Parts is a list of nonnegative integers and minimum is a positive
integer. Drop only trailing zero components, keeping at least minimum
components. Right-pad with zeros if the list was shorter than minimum,
including an empty list. Return the resulting components joined by dots,
without changing parts.
