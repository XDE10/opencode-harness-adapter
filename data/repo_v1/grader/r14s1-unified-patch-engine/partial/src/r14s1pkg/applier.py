from r14s1pkg.models import Hunk, PatchConflictError, PatchResult
from r14s1pkg.parser import parse_unified_diff


def _candidate_deltas(max_fuzz: int) -> list[int]:
    deltas = [0]
    for step in range(1, max_fuzz + 1):
        deltas.append(-step)
        deltas.append(step)
    return deltas


def apply_hunks(
    original_text: str,
    hunks: list[Hunk],
    max_fuzz: int = 0,
) -> PatchResult:
    if max_fuzz < 0:
        raise ValueError("max_fuzz must be non-negative")

    working_lines = original_text.splitlines()
    applied_offsets: list[int] = []
    cumulative_offset = 0

    for idx, hunk in enumerate(hunks):
        hunk.validate()
        base_idx = 0 if (hunk.old_start == 0 and hunk.old_count == 0) else (hunk.old_start - 1)
        expected_idx = base_idx + cumulative_offset
        target_old = hunk.old_lines()

        matched_idx: int | None = None
        used_delta = 0

        for delta in _candidate_deltas(max_fuzz):
            cand_idx = expected_idx + delta
            if cand_idx < 0 or cand_idx + hunk.old_count > len(working_lines):
                continue
            if working_lines[cand_idx : cand_idx + hunk.old_count] == target_old:
                matched_idx = cand_idx
                used_delta = delta
                break

        if matched_idx is None:
            raise PatchConflictError(
                f"Hunk #{idx} failed to apply at expected line {expected_idx + 1}",
                hunk_index=idx,
            )

        working_lines[matched_idx : matched_idx + hunk.old_count] = hunk.new_lines()
        applied_offsets.append(used_delta)
        cumulative_offset = used_delta

    return PatchResult(
        text="\n".join(working_lines),
        applied_offsets=applied_offsets,
    )


def apply_patch(
    original_text: str,
    diff_text: str,
    max_fuzz: int = 0,
) -> PatchResult:
    hunks = parse_unified_diff(diff_text)
    return apply_hunks(original_text, hunks, max_fuzz=max_fuzz)
