Fix `route_request(routes, path)` in `solution.py`.

Implement a deterministic URL path-template router.

Inputs:
- `routes` must be a `list`. Each route must be a `dict` containing string keys `"name"` and `"template"`; extra keys are ignored. All routes are validated before matching.
- `path` must be a `str` absolute path starting with `/`. The root path `"/"` has zero segments. Other paths are split on `/`; empty segments (leading beyond the first slash, consecutive slashes, or trailing slash) are invalid. No URL decoding or query parsing is performed.

Template syntax:
- A template is also an absolute path string with the same empty-segment rule.
- A segment exactly equal to `"*"` is a wildcard and is allowed only as the final segment. It matches zero or more remaining path segments.
- A segment starting with `":"` is a parameter. The text after `":"` must match `[A-Za-z_][A-Za-z0-9_]*`, must not be `"wildcard"`, and parameter names must be unique within a template. A parameter matches exactly one path segment.
- Any other nonempty segment is a literal and matches case-sensitively.

Return:
- If no route matches, return `None`.
- Otherwise return `{"name": <route name>, "params": <dict>}`.
- Each parameter contributes one entry mapping its name to the matched path segment string.
- A wildcard contributes `"wildcard": [matched, segments, ...]`, including `[]` when it matches zero segments.

Tie-breaking among matching routes:
- Compare segment kinds left-to-right over overlapping template segments with ranks literal=2, parameter=1, wildcard=0; the first larger rank wins.
- If all overlapping ranks are equal and lengths differ, the longer template wins unless its only extra segment is a final wildcard, in which case the shorter template wins.
- If still tied, the earlier route in `routes` wins.

Raise `ValueError` for any invalid `path`, invalid `routes` container, invalid route entry, or invalid template. The path is validated before routes.

Examples:
`route_request([{"name": "user", "template": "/users/:id"}], "/users/42")` returns `{"name": "user", "params": {"id": "42"}}`.

`route_request([{"name": "files", "template": "/files/*"}], "/files")` returns `{"name": "files", "params": {"wildcard": []}}`.
