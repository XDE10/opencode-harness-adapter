Fix `match_route(pattern, path)` in `solution.py`.

Return `True` iff `path` matches route `pattern`, otherwise `False`.

Both inputs must be strings; otherwise raise `TypeError`. Split both strings on `/` into segments. Empty segments (from leading, trailing, or repeated slashes) are ordinary segments and must match exactly unless covered by a final `**`. Matching is case-sensitive.

Within a normal segment:
- `?` matches exactly one character.
- `*` matches zero or more characters, including zero at the beginning or end of a segment and including an empty segment.
- `\` escapes the next character, so `\*`, `\?`, and `\\` match literal `*`, `?`, and `\`; a backslash before any other character also matches that character literally. A trailing backslash raises `ValueError`.

A segment equal to exactly `**` is recursive. It is allowed only as the final pattern segment; if it appears earlier, raise `ValueError`. A final `**` matches zero or more complete path segments, so `api/**` matches `api`, `api/`, and `api/v1/x`. A segment such as `a**b` is not recursive; it is a normal segment containing two `*` wildcards.

Examples:
`match_route("/img/logo?.png", "/img/logo2.png")` returns `True`.
`match_route("api/**", "api")` returns `True`.
