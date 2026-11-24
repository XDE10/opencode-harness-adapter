# Unified Diff Parser & Stateful Patch Applier (`r14s1pkg`)

## Background
`r14s1pkg` parses unified diff text into structured `Hunk` models and applies multi-hunk patches sequentially against source files with configurable line-offset fuzzing.

We received two bug reports from production users:
1. **Single-line hunks fail header validation or corrupt line counts**: Unified diffs produced by standard `git diff` or `diff -u` omit the `,count` portion in the `@@ -start,count +start,count @@` header when `count` is `1` (e.g., `@@ -3 +3,2 @@` or `@@ -1,2 +1 @@`) and can also have `count` equal to `0` for pure insertions/deletions (e.g. `@@ -0,0 +1,2 @@`). Currently, parsing or validating such hunks fails or computes the wrong expected line totals.
2. **Multi-hunk patches with net line insertions/deletions misalign subsequent hunks**: When applying a patch with multiple hunks sequentially, if an earlier hunk adds or removes lines (or applies at a fuzzed offset), later hunks are applied at the wrong target position in the mutated document or fail to match altogether.

---

## Behavioral Specification

### 1. Hunk Model & Validation (`r14s1pkg.models`)
- `HunkLine(op: str, text: str)`:
  - `op` is one of `' '` (context), `'-'` (deletion), `'+'` (addition).
  - `text` is the line content without the leading op character or trailing newline.
- `Hunk(old_start: int, old_count: int, new_start: int, new_count: int, lines: list[HunkLine], section: str = "")`:
  - `old_lines() -> list[str]`: returns the `text` of all lines in `lines` whose `op` is `' '` or `'-'`.
  - `new_lines() -> list[str]`: returns the `text` of all lines in `lines` whose `op` is `' '` or `'+'`.
  - `net_delta() -> int`: returns `new_count - old_count`.
  - `validate() -> None`: raises `ValueError` if `len(self.old_lines()) != self.old_count` or `len(self.new_lines()) != self.new_count`.

### 2. Unified Diff Parser (`r14s1pkg.parser`)
- `parse_unified_diff(diff_text: str) -> list[Hunk]`:
  - Ignores file headers (`--- ...`, `+++ ...`, `diff --git ...`, `index ...`).
  - Parses hunk headers of the form:
    `@@ -<old_start>[,<old_count>] +<new_start>[,<new_count>] @@[ <section>]`
  - If `,<old_count>` or `,<new_count>` is omitted in the header, its count defaults to `1`. If explicitly `0` (e.g. `-0,0`), the count is `0`.
  - Optional trailing section header text after `@@` is stripped of leading/trailing whitespace and stored in `Hunk.section`.
  - Parses body lines starting with `' '`, `'-'`, or `'+'` into `HunkLine(op, content)`. An empty line inside a hunk body is treated as a context line (`op=' '`, `text=''`). Lines starting with `\` (e.g., `\ No newline at end of file`) are ignored.
  - Calls `hunk.validate()` on every parsed hunk before returning the list of hunks.
  - Raises `ValueError` on malformed hunk headers, unexpected body lines, or if `hunk.validate()` fails.

### 3. Stateful Patch Applier (`r14s1pkg.applier`)
- `apply_hunks(original_text: str, hunks: list[Hunk], max_fuzz: int = 0) -> PatchResult`:
  - Splits `original_text` into lines (`splitlines()`).
  - Tracks cumulative line shift (`cumulative_offset`, initially `0`) across hunks as the working line buffer grows or shrinks.
  - For each `hunk` in `hunks`:
    - The expected 0-based target index in the current working buffer is:
      - `expected_idx = (hunk.old_start - 1) + cumulative_offset` when `hunk.old_count > 0` (or `hunk.old_start > 0`).
      - If `hunk.old_start == 0` and `hunk.old_count == 0` (pure insertion at start of empty/new file), `expected_idx = 0 + cumulative_offset`.
    - Searches for a matching slice of length `hunk.old_count` equal to `hunk.old_lines()` around `expected_idx` within `[-max_fuzz, +max_fuzz]`:
      - Candidate shifts `delta` are tested in order of increasing `abs(delta)`, breaking ties by negative `delta` first (`0, -1, +1, -2, +2, ...`).
      - Candidate index `cand_idx = expected_idx + delta` must satisfy `0 <= cand_idx <= len(working_lines) - hunk.old_count`.
    - If no candidate matches, raises `PatchConflictError` with `hunk_index` (0-based).
    - Replaces `working_lines[matched_idx : matched_idx + hunk.old_count]` with `hunk.new_lines()`.
    - Updates `cumulative_offset` by adding both the fuzz `delta` used for this hunk (`matched_idx - expected_idx`) AND `hunk.net_delta()`, so subsequent hunks target the properly shifted line positions.
    - Records the applied fuzz `delta` (`matched_idx - expected_idx`) in `PatchResult.applied_offsets`.
  - Returns `PatchResult(text="\n".join(working_lines), applied_offsets=...)`.
