Fix `crt(congruences)` in `solution.py`.

Implement a deterministic Chinese remainder solver.

Input:
- `congruences` must be a list. Each item must be a list `[a, m]` of exactly two integers; booleans are not accepted as integers.
- Every modulus `m` must be positive.
- Negative residues `a` are allowed and must first be normalized to their least nonnegative residue modulo `m` (for example, `-1 mod 5 = 4`).

Output:
- Return `[x, m]`, where `m` is the least common multiple of all input moduli, and `x` is the least nonnegative integer satisfying every congruence modulo `m`.
- For an empty input list, return `[0, 1]`.
- Moduli need not be pairwise coprime. If two congruences are inconsistent, raise `ValueError`.
- Any invalid input described above must raise `ValueError`.

Examples:
- `crt([[2, 3], [3, 5], [2, 7]])` returns `[23, 105]`.
- `crt([[-2, 5], [1, 4]])` returns `[13, 20]`.
- `crt([[1, 4], [2, 6]])` raises `ValueError`.
