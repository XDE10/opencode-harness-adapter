# Issue Report: Patch Queue Fuzz Offset Drift & 3-Way Adjacent Region Merge Failure

## Overview
`r14s2pkg` provides a unified diff hunk parser, a fuzz-tolerant patch queue applier with atomic transaction rollback (`PatchSession`), and a region-based 3-way merge resolver (`three_way_merge`).

Two production issues have been reported when composing multi-hunk patches with fuzz shifts and when merging adjacent/Insertion-only edits in 3-way merges:

### Issue 1: Cumulative Line Offset Drift After Fuzz-Shifted Hunks in `PatchSession`
When a unified diff contains multiple hunks (`@@ -old_start,old_count +new_start,new_count @@`), each subsequent hunk's expected start position in the working buffer must account for all prior hunks applied in the same patch:
- Every hunk has a nominal 0-based target index in the current buffer equal to `(hunk.old_start - 1) + cumulative_offset` (or `0` when `hunk.old_start == 0` for empty-file creation).
- When a hunk matches with a non-zero fuzz shift `delta` (searching `[-max_fuzz, +max_fuzz]` in increasing order of `abs(delta)`, breaking ties toward negative `delta`), the actual applied position is `expected_pos + delta`.
- **Specification**: After applying a hunk at `actual_pos`, `cumulative_offset` for subsequent hunks in the same patch MUST be updated by `(len(replacement_lines) - len(source_lines)) + delta`. Currently, `delta` is ignored when updating `cumulative_offset`, causing subsequent hunks in a shifted file to look at the wrong line offset and fail (or apply at the wrong location).
- Furthermore, `PatchSession.apply_patch` and `PatchSession.rollback_to(checkpoint_id)` must guarantee strict state isolation: a failed multi-hunk patch must leave the session buffer and history completely unmodified, and rolling back to a checkpoint must restore the exact document lines and discard invalidated history entries after that checkpoint.

### Issue 2: False Conflict on Pure Insertions & Adjacent Edits in `three_way_merge`
`three_way_merge(base, ours, theirs)` computes changed regions against `base` for both `ours` and `theirs` (`ChangeRegion(base_start, base_end, replacement)` where `[base_start, base_end)` is a 0-based half-open slice of `base`).
- **Specification**:
  1. Two regions overlap (and therefore conflict, unless their `replacement` sequences are identical) if and only if:
     - Both regions span a non-empty range or the same insertion point in `base` that actually intersects:
       - If both regions are pure insertions (`a.base_start == a.base_end` and `b.base_start == b.base_end`), they conflict if and only if `a.base_start == b.base_start` (and `a.replacement != b.replacement`).
       - Otherwise, two regions `[a.base_start, a.base_end)` and `[b.base_start, b.base_end)` overlap if and only if `max(a.base_start, b.base_start) < min(a.base_end, b.base_end)`, OR a pure insertion `a` (`a.base_start == a.base_end`) lies strictly inside a non-empty modified range `b` (`b.base_start < a.base_start < b.base_end`, and symmetrically if `b` is a pure insertion inside `a`).
     - Touching/adjacent regions where `a.base_end == b.base_start` (including a pure insertion at the exact boundary `b.base_start` or `b.base_end` of a replacement region) do **not** conflict! They must both be applied in `(base_start, base_end)` order (a pure insertion at `pos` orders before a replacement starting at `pos`, and after a replacement ending at `pos`).
  2. Identical changes (`a.base_start == b.base_start and a.base_end == b.base_end and a.replacement == b.replacement`) must be deduplicated cleanly without emitting conflict markers.
  3. Conflicting regions must emit standard conflict markers:
     ```
     <<<<<<< OURS
     ...ours lines...
     =======
     ...theirs lines...
     >>>>>>> THEIRS
     ```
     spanning the union `[min(a.base_start, b.base_start), max(a.base_end, b.base_end))` in `base`.
