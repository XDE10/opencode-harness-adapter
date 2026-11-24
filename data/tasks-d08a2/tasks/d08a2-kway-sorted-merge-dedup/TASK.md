Fix `merge_sorted(streams, keys, dedup)` in `solution.py`.

Implement a deterministic k-way merge over already sorted streams of dictionaries.

Inputs:
- `streams`: list of lists of dicts. Each inner stream is sorted nondecreasing by the tuple of values selected by `keys`. Streams may be empty.
- `keys`: non-empty list of strings. The sort key for an item is `(item[keys[0]], item[keys[1]], ...)`. Key values in tests are mutually comparable and hashable JSON ints or strings.
- `dedup`: one of `"none"`, `"first"`, `"last"`.

Merge order:
- Always compare key tuples first.
- If two items have the same key tuple, the item from the smaller stream index comes first.
- If two such items are in the same stream, the earlier position comes first.

Dedup is applied after the full merge and is based only on the key tuple:
- `"none"`: keep every item.
- `"first"`: keep only the earliest item for each key tuple, at its original merged position.
- `"last"`: keep only the latest item for each key tuple, at the position where that latest item occurred; remove earlier duplicates.

Return the resulting list of original dictionaries. Do not mutate `streams` or the dictionaries.

Raise `ValueError` if `keys` is not a non-empty list of strings, if `dedup` is not one of the three strings, if `streams` is not a list of lists of dicts, or if any item is missing a required key.

Examples:
`merge_sorted([[{"k":1,"id":"a"},{"k":3,"id":"c"}], [{"k":2,"id":"b"}]], ["k"], "none")` returns `[{"k":1,"id":"a"},{"k":2,"id":"b"},{"k":3,"id":"c"}]`.

`merge_sorted([[{"k":1,"id":"a"},{"k":1,"id":"b"},{"k":2,"id":"c"}]], ["k"], "last")` returns `[{"k":1,"id":"b"},{"k":2,"id":"c"}]`.
