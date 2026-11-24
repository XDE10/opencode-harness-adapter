from r06s3pkg import FilterRegistry, TemplateEngine


def test_basic_variable_and_filter():
    engine = TemplateEngine()
    result = engine.render("Hello {{ user.name | upper }}!", {"user": {"name": "ada"}})
    assert result == "Hello ADA!"


def test_if_else_rendering():
    engine = TemplateEngine()
    tpl = "{% if active %}ON{% else %}OFF{% endif %}"
    assert engine.render(tpl, {"active": True}) == "ON"
    assert engine.render(tpl, {"active": False}) == "OFF"


def test_simple_for_loop():
    engine = TemplateEngine()
    tpl = "{% for x in items %}{{ loop.index }}:{{ x }};{% endfor %}"
    assert engine.render(tpl, {"items": ["a", "b"]}) == "1:a;2:b;"
