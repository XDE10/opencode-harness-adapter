Fix `canonical_duration(text)` in `solution.py`.

Implement a deterministic compound-duration canonicalizer.

Input:
- `text` must be a `str`; otherwise raise `TypeError`.
- A valid string is one or more terms separated by exactly one ASCII space. There must be no leading or trailing spaces and no repeated spaces.
- Each term is one or more ASCII decimal digits immediately followed by exactly one lowercase unit letter from `w`, `d`, `h`, `m`, `s`. Leading zeros in amounts are allowed. Signs, decimals, tabs, newlines, uppercase units, unknown units, empty terms, and any other characters are invalid.
- Terms may appear in any order and may repeat. Repeated units add their amounts before conversion.

Raise `ValueError` for every invalid string, including the empty string.

Conversion:
- `1w = 604800s`, `1d = 86400s`, `1h = 3600s`, `1m = 60s`, `1s = 1s`.
- Convert the total seconds into weeks, days, hours, minutes, seconds using the largest units first; days are the remainder after weeks.
- Omit zero fields. If the total is zero, return `"0s"`.

Output:
- Return a single `str` with non-zero fields ordered `w d h m s` and separated by single spaces.
- If there is only one field, print it without padding.
- If there are multiple fields, the first field is never padded; among the remaining fields, only minute (`m`) and second (`s`) values are zero-padded to at least two digits. Week, day, and hour values are never padded.

Examples:
`canonical_duration("8d")` returns `"1w 1d"`.
`canonical_duration("2d 3h 04m")` returns `"2d 3h 04m"`.
