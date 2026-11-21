# Return the last match in a slice

Fix `last_index(items, needle, start=0, stop=None)` in `solution.py`.

Return the last absolute index at which needle is equal to an item in
items[start:stop]. Use normal Python slice bounds, including negative
offsets, clipping, and exclusive stop. Return -1 when there is no match.
