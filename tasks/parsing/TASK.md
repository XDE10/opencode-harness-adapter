Fix `parse_settings(text)` in `solution.py`. Parse one `key=value`
assignment per line into a dictionary of strings. Ignore blank lines and
whole-line comments (after leading whitespace). Split on the first equals
sign; trim both fields and keep any further equals signs. Empty values are
valid. Raise ValueError for a noncomment line without an equals sign, an empty
key, or a duplicate key after trimming. Keep the public function signature.
