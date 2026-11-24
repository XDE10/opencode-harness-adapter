from r15s2lint import lint_code


def test_detects_unused_import_and_used_import():
    src = (
        "import os\n"
        "import sys\n"
        "print(os.name)\n"
    )
    diags = lint_code(src)
    assert [(d.line, d.code, d.symbol) for d in diags] == [(2, "L101", "sys")]


def test_detects_bare_except_and_blanket_noqa():
    src = (
        "try:\n"
        "    x = 1\n"
        "except:\n"
        "    pass\n"
        "try:\n"
        "    y = 2\n"
        "except:  # noqa\n"
        "    pass\n"
    )
    diags = lint_code(src)
    assert [(d.line, d.code) for d in diags] == [(3, "L103")]
