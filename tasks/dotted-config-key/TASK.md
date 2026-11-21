# Resolve a setting with literal dotted keys

Fix `lookup(config, path, default=None)` in `solution.py`.

Config is a dictionary and path is a nonempty dotted string with
nonempty components. At each dictionary, first look for a literal key
matching the entire remaining path. If absent, descend through the key
before the first dot and repeat. Return default if a lookup is missing
or would descend into a nondictionary. A present null is a value.
