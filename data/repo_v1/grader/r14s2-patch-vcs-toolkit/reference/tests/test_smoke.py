from r14s2pkg import PatchSession, parse_unified_diff, three_way_merge


def test_parse_and_apply_simple_patch():
    initial = ["alpha", "beta", "gamma", "delta"]
    diff = "\n".join([
        "--- a/file.txt",
        "+++ b/file.txt",
        "@@ -2,2 +2,3 @@",
        " beta",
        "-gamma",
        "+GAMMA_1",
        "+GAMMA_2",
    ])
    hunks = parse_unified_diff(diff)
    assert len(hunks) == 1
    session = PatchSession(initial)
    cp = session.apply_patch(diff, patch_name="p1")
    assert cp == 1
    assert session.lines == ["alpha", "beta", "GAMMA_1", "GAMMA_2", "delta"]


def test_simple_three_way_merge_disjoint():
    base = ["line1", "line2", "line3", "line4", "line5"]
    ours = ["LINE1", "line2", "line3", "line4", "line5"]
    theirs = ["line1", "line2", "line3", "line4", "LINE5"]
    res = three_way_merge(base, ours, theirs)
    assert not res.has_conflicts
    assert res.lines == ["LINE1", "line2", "line3", "line4", "LINE5"]
