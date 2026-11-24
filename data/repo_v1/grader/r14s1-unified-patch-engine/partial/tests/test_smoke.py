from r14s1pkg import apply_patch, parse_unified_diff


def test_parse_and_apply_simple_replacement() -> None:
    original = "alpha\nbeta\ngamma\n"
    diff = (
        "--- a/file.txt\n"
        "+++ b/file.txt\n"
        "@@ -1,3 +1,3 @@\n"
        " alpha\n"
        "-beta\n"
        "+BETA\n"
        " gamma\n"
    )
    hunks = parse_unified_diff(diff)
    assert len(hunks) == 1
    assert hunks[0].old_count == 3
    assert hunks[0].new_count == 3

    result = apply_patch(original, diff)
    assert result.text == "alpha\nBETA\ngamma"
    assert result.applied_offsets == [0]


def test_apply_with_fuzz_offset() -> None:
    original = "preamble\nalpha\nbeta\ngamma\n"
    diff = (
        "@@ -1,3 +1,3 @@\n"
        " alpha\n"
        "-beta\n"
        "+BETA\n"
        " gamma\n"
    )
    result = apply_patch(original, diff, max_fuzz=2)
    assert result.text == "preamble\nalpha\nBETA\ngamma"
    assert result.applied_offsets == [1]
