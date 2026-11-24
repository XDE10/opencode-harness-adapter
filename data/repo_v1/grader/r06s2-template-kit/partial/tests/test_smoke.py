from r06s2pkg import FilterRegistry, TemplateEngine


def test_basic_variable_and_single_filter() -> None:
    engine = TemplateEngine()
    result = engine.render("Hello {{ name | upper }}!", {"name": "alice"})
    assert result == "Hello ALICE!"


def test_basic_if_else_and_for() -> None:
    engine = TemplateEngine()
    tpl = "{% if show %}Items:{% for x in items %} {{ x }}{% endfor %}{% else %}None{% endif %}"
    assert engine.render(tpl, {"show": True, "items": ["a", "b"]}) == "Items: a b"
    assert engine.render(tpl, {"show": False, "items": ["a", "b"]}) == "None"


def test_custom_filter_registration() -> None:
    reg = FilterRegistry()
    reg.register("double", lambda v: f"{v}{v}", invalidate_empty=True)
    engine = TemplateEngine(registry=reg)
    assert engine.render("{{ word | double }}", {"word": "hi"}) == "hihi"
