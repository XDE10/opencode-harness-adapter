import pytest
from r14s1pkg import (
    Hunk,
    HunkLine,
    PatchConflictError,
    apply_hunks,
    apply_patch,
    parse_unified_diff,
)


def test_parse_section_and_no_newline_marker() -> None:
    diff = (
        "diff --git a/main.py b/main.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/main.py\n"
        "+++ b/main.py\n"
        "@@ -1,2 +1,2 @@ def greet():\n"
        " print('hi')\n"
        "-print('bye')\n"
        "+print('goodbye')\n"
        "\\ No newline at end of file\n"
    )
    hunks = parse_unified_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].section == "def greet():"
    assert hunks[0].old_lines() == ["print('hi')", "print('bye')"]
    assert hunks[0].new_lines() == ["print('hi')", "print('goodbye')"]


def test_parse_explicit_zero_count_new_file() -> None:
    diff = (
        "--- /dev/null\n"
        "+++ b/added.txt\n"
        "@@ -0,0 +1,2 @@\n"
        "+first\n"
        "+second\n"
    )
    hunks = parse_unified_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].old_start == 0
    assert hunks[0].old_count == 0
    assert hunks[0].new_count == 2
    res = apply_hunks("", hunks)
    assert res.text == "first\nsecond"


def test_conflict_raises_with_hunk_index() -> None:
    original = "line1\nline2\nline3\n"
    diff = (
        "@@ -1,2 +1,2 @@\n"
        " line1\n"
        "-wrong_line\n"
        "+replacement\n"
    )
    with pytest.raises(PatchConflictError) as exc_info:
        apply_patch(original, diff, max_fuzz=1)
    assert exc_info.value.hunk_index == 0


def test_fuzz_tie_breaking_prefers_negative_offset() -> None:
    original = "target\nmid\ntarget\n"
    hunk = Hunk(
        old_start=2,
        old_count=1,
        new_start=2,
        new_count=1,
        lines=[HunkLine("-", "target"), HunkLine("+", "REPLACED")],
    )
    result = apply_hunks(original, [hunk], max_fuzz=1)
    assert result.applied_offsets == [-1]
    assert result.text == "REPLACED\nmid\ntarget"


def test_parse_omitted_single_line_counts_both_sides() -> None:
    diff = (
        "@@ -1 +1 @@\n"
        "-old_single\n"
        "+new_single\n"
    )
    hunks = parse_unified_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].old_count == 1
    assert hunks[0].new_count == 1
    res = apply_hunks("old_single\n", hunks)
    assert res.text == "new_single"


def test_parse_omitted_count_on_one_side_only() -> None:
    diff_expand = (
        "@@ -2 +2,3 @@\n"
        "-middle\n"
        "+middle_1\n"
        "+middle_2\n"
        "+middle_3\n"
    )
    hunks = parse_unified_diff(diff_expand)
    assert hunks[0].old_count == 1
    assert hunks[0].new_count == 3

    diff_shrink = (
        "@@ -2,3 +2 @@\n"
        "-middle_1\n"
        "-middle_2\n"
        "+middle\n"
        "-middle_3\n"
    )
    hunks_shrink = parse_unified_diff(diff_shrink)
    assert hunks_shrink[0].old_count == 3
    assert hunks_shrink[0].new_count == 1


def test_multi_hunk_with_line_insertions_and_deletions() -> None:
    original = "\n".join([f"line{i}" for i in range(1, 11)])
    diff = (
        "@@ -2,2 +2,4 @@\n"
        " line2\n"
        "+inserted_a\n"
        "+inserted_b\n"
        " line3\n"
        "@@ -8,2 +10,1 @@\n"
        "-line8\n"
        " line9\n"
    )
    result = apply_patch(original, diff, max_fuzz=0)
    assert result.applied_offsets == [0, 0]
    assert result.text.splitlines() == [
        "line1",
        "line2",
        "inserted_a",
        "inserted_b",
        "line3",
        "line4",
        "line5",
        "line6",
        "line7",
        "line9",
        "line10",
    ]


def test_multi_hunk_cumulative_fuzz_and_net_delta() -> None:
    original = "\n".join(["extra_top", "a", "b", "c", "d", "e", "f", "g"])
    hunk1 = Hunk(
        old_start=1,
        old_count=2,
        new_start=1,
        new_count=4,
        lines=[
            HunkLine(" ", "a"),
            HunkLine("+", "a1"),
            HunkLine("+", "a2"),
            HunkLine(" ", "b"),
        ],
    )
    hunk2 = Hunk(
        old_start=6,
        old_count=2,
        new_start=8,
        new_count=1,
        lines=[
            HunkLine("-", "f"),
            HunkLine(" ", "g"),
        ],
    )
    result = apply_hunks(original, [hunk1, hunk2], max_fuzz=1)
    assert result.applied_offsets == [1, 0]
    assert result.text.splitlines() == [
        "extra_top",
        "a",
        "a1",
        "a2",
        "b",
        "c",
        "d",
        "e",
        "g",
    ]


def test_three_hunks_sequential_drift_without_fuzz() -> None:
    original = "\n".join(["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9"])
    diff = (
        "@@ -1,2 +1,1 @@\n"
        "-L1\n"
        " L2\n"
        "@@ -4,2 +3,4 @@\n"
        " L4\n"
        "+L4_a\n"
        "+L4_b\n"
        " L5\n"
        "@@ -8,2 +9,2 @@\n"
        " L8\n"
        "-L9\n"
        "+L9_mod\n"
    )
    result = apply_patch(original, diff, max_fuzz=0)
    assert result.applied_offsets == [0, 0, 0]
    assert result.text.splitlines() == [
        "L2",
        "L3",
        "L4",
        "L4_a",
        "L4_b",
        "L5",
        "L6",
        "L7",
        "L8",
        "L9_mod",
    ]
