Fix `run_pointer(doc, ops)` in `solution.py`.

Implement a deterministic JSON Pointer-style tree transformer. `doc` is a JSON-like value made only of `dict` with string keys, `list`, `str`, `int`, `bool`, and `None`. `ops` is a list of operation dicts. The function must not mutate `doc` or `ops`; work on a deep copy and return:

`{"results": [...], "doc": final_doc}`

For each operation, append one result:
- `{"op": "get", "path": p}`: append a deep copy of the current value at `p`.
- `{"op": "set", "path": p, "value": v}`: deep-copy `v`, store it at `p`, append `None`.
- `{"op": "remove", "path": p}`: remove the value at `p`, append `None`.

Path syntax:
- `""` is the whole document.
- Any other path must start with `/`; otherwise raise `ValueError`.
- Split after the leading `/`; empty tokens are valid object keys.
- Decode each token by scanning left-to-right: `~0` becomes `~`, `~1` becomes `/`, and any other `~` escape raises `ValueError`. Decoding is not repeated after replacement, so token `~01` means the literal key `~1`, not `/`.

Traversal and final access:
- For a `dict`, a token is a string key. Missing key raises `KeyError` for `get`/`remove`; `set` creates or updates it. Token `-` is an ordinary dict key.
- For a `list`, a token must be a canonical decimal index: digits only, no leading zeros except `0`. Invalid indices raise `IndexError`.
- For `get`/`remove`, a list index must satisfy `0 <= i < len(list)`. Token `-` is invalid and raises `IndexError`.
- For `set` on a list, token `-` appends. A numeric index equal to `len(list)` appends; an index greater than `len(list)` raises `IndexError`.
- Traversing into or targeting a scalar raises `TypeError`.
- Root `get` returns the whole current document; root `set` replaces the whole document; root `remove` raises `ValueError`.

Invalid `ops`, invalid operation dicts, unknown operation names, non-string paths, and `set` operations missing the `value` key raise `ValueError`. If any operation raises, the whole call raises that exception.

Examples:
`run_pointer({"a": [1, 2]}, [{"op": "set", "path": "/a/-", "value": 3}, {"op": "get", "path": "/a/1"}])` returns `{"results": [null, 2], "doc": {"a": [1, 2, 3]}}`.

`run_pointer({"a/b": 7}, [{"op": "get", "path": "/a~1b"}])` returns `{"results": [7], "doc": {"a/b": 7}}`.
