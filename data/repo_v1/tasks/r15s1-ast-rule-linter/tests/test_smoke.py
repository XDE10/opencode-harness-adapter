from pylintlet import LinterEngine


def test_unused_import_detected():
    source = "import os\nimport sys\nprint(sys.version)\n"
    engine = LinterEngine()
    diags = engine.lint_source(source)
    assert len(diags) == 1
    assert diags[0].code == "L101"
    assert diags[0].line == 1
    assert "os" in diags[0].message


def test_mutable_default_detected_and_blanket_noqa():
    source = (
        "def bad(items=[]):\n"
        "    return items\n"
        "def ok(items={}):  # noqa\n"
        "    return items\n"
    )
    engine = LinterEngine()
    diags = engine.lint_source(source)
    assert len(diags) == 1
    assert diags[0].code == "L102"
    assert diags[0].line == 1
