Fix `diff_hunks(a, b)` in `solution.py`.

Implement a deterministic line-diff hunk generator.

Inputs:
- `a` and `b` are lists of strings, possibly empty.
- Return a list of hunks. Each hunk is a dict with exactly these keys:
  - `"op"`: one of `"equal"`, `"delete"`, `"insert"`.
  - `"a_start"`, `"a_end"`: half-open range in `a`.
  - `"b_start"`, `"b_end"`: half-open range in `b`.

Algorithm:
- Let `dp[i][j]` be the LCS length of suffixes `a[i:]` and `b[j:]`.
- Walk from `(0, 0)` to `(n, m)` in script order:
  1. If `a[i] == b[j]`, emit `"equal"` and advance both.
  2. Otherwise, emit `"delete"` if `j == m` or `dp[i+1][j] >= dp[i][j+1]`; advance `i`.
  3. Otherwise emit `"insert"` and advance `j`.
- For a delete hunk, `b_start == b_end == j`; for an insert hunk, `a_start == a_end == i`.
- After emitting raw one-line operations, merge consecutive operations of the same kind only when the previous hunk's `a_end` equals the next `a_start` and the previous `b_end` equals the next `b_start`. Update the merged hunk's `a_end` and `b_end`.
- If both inputs are empty, return `[]`.
- Inputs are assumed valid; no exception behavior is graded.

Examples:
`diff_hunks(["u", "v"], ["v", "u"])` returns `[{"op":"delete","a_start":0,"a_end":1,"b_start":0,"b_end":0}, {"op":"equal","a_start":1,"a_end":2,"b_start":0,"b_end":1}, {"op":"insert","a_start":2,"a_end":2,"b_start":1,"b_end":2}]`.

`diff_hunks(["x", "y"], [])` returns `[{"op":"delete","a_start":0,"a_end":2,"b_start":0,"b_end":0}]`.
