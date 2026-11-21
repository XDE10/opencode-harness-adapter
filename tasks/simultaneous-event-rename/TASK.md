# Rename fields in an event snapshot

Fix `rename_fields(event, mapping)` in `solution.py`.

Both inputs are dictionaries. Mapping maps source field names to
destination names, with distinct destinations. Apply renames
simultaneously to a copy. A present field that is not a source keeps
its value if a rename targets it. An absent source has no effect.
Swaps and longer cycles use values from the original event.
