import pytest
from r14s2pkg import PatchError, PatchSession, parse_unified_diff, three_way_merge


def test_hunk_parser_validation_and_counts():
    bad_diff = "\n".join([
        "--- a/f",
        "+++ b/f",
        "@@ -1,2 +1,2 @@",
        " only_one_line",
    ])
    with pytest.raises(PatchError):
        parse_unified_diff(bad_diff)


def test_session_atomic_failure_and_rollback():
    initial = ["a", "b", "c", "d", "e"]
    session = PatchSession(initial, max_fuzz=1)
    p1 = "\n".join([
        "@@ -1,2 +1,2 @@",
        "-a",
        "+A",
        " b",
    ])
    cp1 = session.apply_patch(p1, "patch1")
    assert session.lines == ["A", "b", "c", "d", "e"]

    bad_multi_hunk = "\n".join([
        "@@ -2,2 +2,2 @@",
        " b",
        "-c",
        "+C",
        "@@ -4,2 +4,2 @@",
        " NON_EXISTENT",
        "-e",
        "+E",
    ])
    with pytest.raises(PatchError):
        session.apply_patch(bad_multi_hunk, "bad_patch")

    # Buffer and history must remain untouched after failed multi-hunk patch
    assert session.lines == ["A", "b", "c", "d", "e"]
    assert len(session.history) == 1

    session.rollback_to(cp1)
    assert session.lines == ["a", "b", "c", "d", "e"]
    assert len(session.history) == 0


def test_three_way_merge_true_conflict_and_identical_dedup():
    base = ["h1", "sep", "body", "footer"]
    ours = ["H1_SAME", "sep", "body_ours", "footer"]
    theirs = ["H1_SAME", "sep", "body_theirs", "footer"]
    res = three_way_merge(base, ours, theirs)
    assert res.has_conflicts
    assert res.conflict_count == 1
    assert res.lines == [
        "H1_SAME",
        "sep",
        "<<<<<<< OURS",
        "body_ours",
        "=======",
        "body_theirs",
        ">>>>>>> THEIRS",
        "footer",
    ]


def test_multi_hunk_cumulative_fuzz_offset_drift():
    initial = [
        "PRE_1",
        "PRE_2",
        "ctx1",
        "old1",
        "ctx2",
        "mid_extra",
        "mid1",
        "mid2",
        "ctx3",
        "old2",
        "ctx4",
    ]
    diff = "\n".join([
        "--- a/app.py",
        "+++ b/app.py",
        "@@ -1,3 +1,4 @@",
        " ctx1",
        "-old1",
        "+new1_a",
        "+new1_b",
        " ctx2",
        "@@ -6,3 +7,3 @@",
        " ctx3",
        "-old2",
        "+new2",
        " ctx4",
    ])
    session = PatchSession(initial, max_fuzz=2)
    cp = session.apply_patch(diff, "shifted_multi_hunk")
    assert cp == 1
    assert session.history[0].fuzz_shifts == (2, 1)
    assert session.lines == [
        "PRE_1",
        "PRE_2",
        "ctx1",
        "new1_a",
        "new1_b",
        "ctx2",
        "mid_extra",
        "mid1",
        "mid2",
        "ctx3",
        "new2",
        "ctx4",
    ]


def test_multi_hunk_negative_fuzz_offset_propagation():
    initial = [
        "k1",
        "v1",
        "k2",
        "mid",
        "k3",
        "v3",
        "k4",
    ]
    diff = "\n".join([
        "@@ -3,3 +3,3 @@",
        " k1",
        "-v1",
        "+V1_NEW",
        " k2",
        "@@ -8,3 +8,3 @@",
        " k3",
        "-v3",
        "+V3_NEW",
        " k4",
    ])
    session = PatchSession(initial, max_fuzz=2)
    session.apply_patch(diff, "neg_shift")
    assert session.history[0].fuzz_shifts == (-2, -1)
    assert session.lines == ["k1", "V1_NEW", "k2", "mid", "k3", "V3_NEW", "k4"]


def test_three_way_merge_adjacent_replacements_no_conflict():
    base = ["a", "b", "c", "d"]
    ours = ["a", "B_OURS", "c", "d"]
    theirs = ["a", "b", "C_THEIRS", "d"]
    res = three_way_merge(base, ours, theirs)
    assert not res.has_conflicts
    assert res.conflict_count == 0
    assert res.lines == ["a", "B_OURS", "C_THEIRS", "d"]


def test_three_way_merge_insertion_adjacent_to_replacement():
    base = ["line1", "line2", "line3"]
    ours = ["line1", "INS_BEFORE_2", "line2", "line3"]
    theirs = ["line1", "LINE2_REPLACED", "line3"]
    res = three_way_merge(base, ours, theirs)
    assert not res.has_conflicts
    assert res.conflict_count == 0
    assert res.lines == ["line1", "INS_BEFORE_2", "LINE2_REPLACED", "line3"]


def test_three_way_merge_pure_insertion_inside_modified_range_conflicts():
    base = ["a", "b", "c", "d"]
    ours = ["a", "BC_OURS", "d"]
    theirs = ["a", "b", "INS_MID", "c", "d"]
    res = three_way_merge(base, ours, theirs)
    assert res.has_conflicts
    assert res.conflict_count == 1
    assert res.lines == [
        "a",
        "<<<<<<< OURS",
        "BC_OURS",
        "=======",
        "b",
        "INS_MID",
        "c",
        ">>>>>>> THEIRS",
        "d",
    ]
