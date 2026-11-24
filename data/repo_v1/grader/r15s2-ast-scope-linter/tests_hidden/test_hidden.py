from r15s2lint import LintEngine, lint_code, parse_noqa_map


def test_import_used_inside_deeply_nested_function_is_not_unused():
    src = (
        "from pathlib import Path\n"
        "def outer():\n"
        "    def inner():\n"
        "        return Path('.')\n"
        "    return inner()\n"
    )
    assert lint_code(src) == []


def test_enabled_rules_filter_and_sorting():
    src = (
        "import json\n"
        "try:\n"
        "    pass\n"
        "except:\n"
        "    pass\n"
    )
    engine = LintEngine()
    only_l103 = engine.lint_source(src, enabled_rules=["l103"])
    assert [(d.line, d.code) for d in only_l103] == [(4, "L103")]


def test_aliased_imports_and_dotted_imports():
    src = (
        "import urllib.parse\n"
        "import collections.abc as cabc\n"
        "from typing import Optional as Opt\n"
        "x = urllib.parse\n"
    )
    diags = lint_code(src)
    assert [(d.line, d.code, d.symbol) for d in diags] == [
        (2, "L101", "cabc"),
        (3, "L101", "Opt"),
    ]


def test_shadowed_import_still_flagged_as_unused_if_never_used_outside():
    src = (
        "import math\n"
        "def compute(math):\n"
        "    return math + 1\n"
    )
    diags = lint_code(src)
    assert [(d.line, d.code, d.symbol) for d in diags] == [
        (1, "L101", "math"),
        (2, "L102", "math"),
    ]


def test_shadow_rollback_preserves_import_for_subsequent_scopes():
    src = (
        "import re\n"
        "def first():\n"
        "    re = 'local'\n"
        "    return re\n"
        "def second():\n"
        "    re = 'again'\n"
        "    return re\n"
    )
    diags = lint_code(src)
    assert [(d.line, d.code, d.symbol) for d in diags] == [
        (1, "L101", "re"),
        (3, "L102", "re"),
        (6, "L102", "re"),
    ]


def test_shadow_in_one_function_used_in_another_marks_import_used():
    src = (
        "import time\n"
        "def shadow_fn(time):\n"
        "    return time\n"
        "def real_user():\n"
        "    return time.time()\n"
    )
    diags = lint_code(src)
    assert [(d.line, d.code, d.symbol) for d in diags] == [
        (2, "L102", "time"),
    ]


def test_specific_noqa_does_not_suppress_different_rule_on_same_line():
    src = (
        "import os  # noqa: L102\n"
        "try:\n"
        "    pass\n"
        "except:  # noqa: L101\n"
        "    pass\n"
    )
    diags = lint_code(src)
    assert [(d.line, d.code) for d in diags] == [
        (1, "L101"),
        (4, "L103"),
    ]


def test_specific_noqa_suppresses_matching_code_case_insensitive():
    src = (
        "import os  # noqa: l101 - intentionally unused\n"
        "import sys\n"
        "def fn(sys):  # noqa: L102, L103\n"
        "    return sys\n"
    )
    diags = lint_code(src)
    assert [(d.line, d.code, d.symbol) for d in diags] == [
        (2, "L101", "sys"),
    ]


def test_noqa_index_multi_code_conflict_resolution():
    src = (
        "import os, sys  # noqa: L102\n"
        "def f(os, sys):  # noqa: l102\n"
        "    pass\n"
    )
    idx = parse_noqa_map(src)
    assert idx.is_suppressed(1, "L102") is True
    assert idx.is_suppressed(1, "L101") is False
    assert idx.is_suppressed(2, "L102") is True
    diags = lint_code(src)
    assert [(d.line, d.code, d.symbol) for d in diags] == [
        (1, "L101", "os"),
        (1, "L101", "sys"),
    ]
