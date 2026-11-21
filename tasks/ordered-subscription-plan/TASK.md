# List each enabled listener once

Fix `listener_order(general, specific, muted=())` in `solution.py`.

General and specific are ordered lists of listener labels, and muted
contains labels to omit entirely. Return a list of distinct unmuted
labels in first-occurrence order, looking at the specific list before
the general list. Label comparisons are exact and case-sensitive.
This function only assembles a list.
