Fix `run(ops)` in `solution.py`.

Implement a deterministic stateful Chinese-remainder solver. The solver maintains one active system of congruences `x ≡ r (mod m)`. State persists across operations until a `reset`.

`ops` is a list of operation dicts. Each dict has the listed keys. `run` returns one output entry per processed operation unless it raises.

Operations:
- `{"op": "add", "r": int, "m": int}`: Add the congruence. `m` must be a positive plain integer and `r` must be a plain integer; `bool` values are not accepted. Otherwise raise `ValueError`. Normalize `r` to its least nonnegative residue modulo `m`. The new congruence must be consistent with every active congruence: residues must agree modulo the gcd of their moduli. A repeated modulus with the same normalized residue is harmless; a repeated modulus with a different normalized residue raises `ValueError`. Append `None`.
- `{"op": "reset"}`: Clear all congruences and return the empty system. Append `None`.
- `{"op": "solve"}`: Append `[x, M]`, where `M` is the least common multiple of all active moduli and `x` is the least nonnegative solution modulo `M`. For an empty system, return `[0, 1]`.
- Any other `op` raises `ValueError`.

Examples:
`run([{"op": "add", "r": 2, "m": 3}, {"op": "add", "r": 3, "m": 5}, {"op": "solve"}])` returns `[None, None, [8, 15]]`.

`run([{"op": "add", "r": 7, "m": 10}, {"op": "reset"}, {"op": "solve"}])` returns `[None, None, [0, 1]]`.

`run([{"op": "add", "r": 1, "m": 2}, {"op": "add", "r": 0, "m": 4}])` raises `ValueError` because the congruences are inconsistent.
