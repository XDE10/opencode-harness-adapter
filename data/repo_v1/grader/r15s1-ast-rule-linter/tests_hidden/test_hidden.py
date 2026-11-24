from pylintlet import LinterEngine, parse_suppressions


def test_basic_unused_and_used_imports():
    source = (
        "import math\n"
        "from collections import deque as dq\n"
        "import pathlib.Path\n"
        "x = dq([1, 2])\n"
    )
    engine = LinterEngine()
    diags = engine.lint_source(source)
    assert [(d.line, d.code, d.message) for d in diags] == [
        (1, "L101", "Unused import 'math'"),
        (3, "L101", "Unused import 'pathlib'"),
    ]


def test_enabled_codes_filtering():
    source = (
        "import os\n"
        "def fn(a=[]):\n"
        "    return a\n"
    )
    only_l102 = LinterEngine(enabled_codes={"L102"}).lint_source(source)
    assert [d.code for d in only_l102] == ["L102"]


def test_unshadowed_import_used_inside_nested_function():
    source = (
        "import json\n"
        "def serialize(payload):\n"
        "    def inner():\n"
        "        return json.dumps(payload)\n"
        "    return inner()\n"
    )
    diags = LinterEngine().lint_source(source)
    assert diags == []


def test_noqa_with_trailing_explanation_and_lowercase():
    source = (
        "import os  # noqa: l101 -- imported for side-effects\n"
        "import sys  # noqa: L102, L101 # legacy reason\n"
        "import math  # noqa: L102 -- wrong code for unused import\n"
    )
    diags = LinterEngine().lint_source(source)
    assert len(diags) == 1
    assert diags[0].line == 3
    assert diags[0].code == "L101"


def test_parse_suppressions_ignores_string_literals_and_normalizes():
    source = (
        'msg = "# noqa: L101"\n'
        "import re  # NOQA: l101 -- regex unused\n"
    )
    smap = parse_suppressions(source)
    assert not smap.is_suppressed(1, "L101")
    assert smap.is_suppressed(2, "L101")
    assert smap.is_suppressed(2, "l101")


def test_function_parameter_shadowing_does_not_mark_outer_import_used():
    source = (
        "import json\n"
        "def format_data(json):\n"
        "    return str(json)\n"
    )
    diags = LinterEngine().lint_source(source)
    assert len(diags) == 1
    assert diags[0].line == 1
    assert diags[0].code == "L101"
    assert "json" in diags[0].message


def test_local_assignment_shadowing_in_function_does_not_mark_outer_import_used():
    source = (
        "from typing import Any\n"
        "def compute():\n"
        "    Any = 42\n"
        "    return Any + 1\n"
    )
    diags = LinterEngine().lint_source(source)
    assert len(diags) == 1
    assert diags[0].line == 1
    assert diags[0].code == "L101"
    assert "Any" in diags[0].message


def test_default_argument_evaluated_in_outer_scope_marks_import_used():
    source = (
        "import json\n"
        "def parse(json=json.loads):\n"
        "    return json('{}')\n"
    )
    diags = LinterEngine().lint_source(source)
    assert diags == []
