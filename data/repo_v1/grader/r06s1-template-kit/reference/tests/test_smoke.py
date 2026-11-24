from r06s1pkg import TemplateEngine


def test_basic_variable_and_filter():
    engine = TemplateEngine()
    result = engine.render("Hello {{ user.name | upper }}!", {"user": {"name": "alice"}})
    assert result == "Hello ALICE!"


def test_if_else_rendering():
    engine = TemplateEngine()
    tpl = "{% if active %}ON{% else %}OFF{% endif %}"
    assert engine.render(tpl, {"active": True}) == "ON"
    assert engine.render(tpl, {"active": False}) == "OFF"


def test_simple_for_loop():
    engine = TemplateEngine()
    tpl = "{% for x in nums %}{{ loop.index }}:{{ x }} {% endfor %}"
    assert engine.render(tpl, {"nums": ["a", "b"]}) == "1:a 2:b "
