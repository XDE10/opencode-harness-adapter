Fix `bencode_codec(mode, payload)` in `solution.py`.

Implement a strict bencode codec for JSON-like values.

- `mode` must be exactly `"encode"` or `"decode"`; otherwise raise `ValueError`.
- Encoding supports only `int` (but not `bool`), `str`, `list`, and `dict` with `str` keys. Any other value, including `float`, `None`, `bool`, or a non-string dict key, raises `TypeError`. Integers may be negative. Strings are encoded as UTF-8 and `<len>` is the number of UTF-8 bytes, not Python characters. Dict keys are emitted in ascending lexicographic order of their UTF-8 byte encodings. The encoder returns a canonical bencoded `str`.
- Decoding requires `payload` to be a `str`; otherwise raise `TypeError`. It must contain exactly one bencoded value with no trailing data; malformed input raises `ValueError`.
- Integer tokens are `i<z>e`, where `<z>` is an optional-minus ASCII decimal integer with no leading zeros, no `+`, and no `-0`.
- String tokens are `<len>:<bytes>`, where `<len>` is an ASCII decimal byte count with no leading zeros except exactly `0`; the bytes must decode as UTF-8.
- Lists are `l<values>e`; dicts are `d<key><value>...e`. Dict keys must decode to strings, and duplicate keys raise `ValueError`. Decoded dict insertion order is not significant.
- The decoder returns `int`, `str`, `list`, or `dict` values only.

Examples:
`bencode_codec("encode", {"b": 1, "a": 2})` returns `"d1:ai1e1:bi2ee"`.
`bencode_codec("decode", "l4:spami42ee")` returns `["spam", 42]`.
