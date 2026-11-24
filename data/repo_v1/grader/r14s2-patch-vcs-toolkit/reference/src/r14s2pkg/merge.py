from __future__ import annotations
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class ChangeRegion:
    base_start: int
    base_end: int
    replacement: tuple[str, ...]
    side: str  # "ours" or "theirs"


@dataclass(frozen=True)
class MergeResult:
    lines: list[str]
    has_conflicts: bool
    conflict_count: int


def diff_regions(base: list[str], target: list[str], side: str) -> list[ChangeRegion]:
    matcher = SequenceMatcher(None, base, target, autojunk=False)
    regions: list[ChangeRegion] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        regions.append(ChangeRegion(i1, i2, tuple(target[j1:j2]), side))
    return regions


def _regions_conflict(a: ChangeRegion, b: ChangeRegion) -> bool:
    a_is_ins = a.base_start == a.base_end
    b_is_ins = b.base_start == b.base_end
    if a_is_ins and b_is_ins:
        return a.base_start == b.base_start
    if a_is_ins:
        return b.base_start < a.base_start < b.base_end
    if b_is_ins:
        return a.base_start < b.base_start < a.base_end
    return max(a.base_start, b.base_start) < min(a.base_end, b.base_end)


def three_way_merge(base: list[str], ours: list[str], theirs: list[str]) -> MergeResult:
    ours_regions = diff_regions(base, ours, "ours")
    theirs_regions = diff_regions(base, theirs, "theirs")

    combined = sorted(
        ours_regions + theirs_regions,
        key=lambda r: (r.base_start, r.base_end, 0 if r.side == "ours" else 1),
    )

    output: list[str] = []
    cursor = 0
    conflict_count = 0
    i = 0

    while i < len(combined):
        curr = combined[i]
        if i + 1 < len(combined):
            nxt = combined[i + 1]
            if (
                curr.side != nxt.side
                and curr.base_start == nxt.base_start
                and curr.base_end == nxt.base_end
                and curr.replacement == nxt.replacement
            ):
                output.extend(base[cursor : curr.base_start])
                output.extend(curr.replacement)
                cursor = curr.base_end
                i += 2
                continue
            if curr.side != nxt.side and _regions_conflict(curr, nxt):
                union_start = min(curr.base_start, nxt.base_start)
                union_end = max(curr.base_end, nxt.base_end)
                ours_reg = curr if curr.side == "ours" else nxt
                theirs_reg = nxt if curr.side == "ours" else curr

                output.extend(base[cursor:union_start])
                output.append("<<<<<<< OURS")
                output.extend(base[union_start : ours_reg.base_start])
                output.extend(ours_reg.replacement)
                output.extend(base[ours_reg.base_end : union_end])
                output.append("=======")
                output.extend(base[union_start : theirs_reg.base_start])
                output.extend(theirs_reg.replacement)
                output.extend(base[theirs_reg.base_end : union_end])
                output.append(">>>>>>> THEIRS")
                cursor = union_end
                conflict_count += 1
                i += 2
                continue

        output.extend(base[cursor : curr.base_start])
        output.extend(curr.replacement)
        cursor = curr.base_end
        i += 1

    output.extend(base[cursor:])
    return MergeResult(lines=output, has_conflicts=conflict_count > 0, conflict_count=conflict_count)
