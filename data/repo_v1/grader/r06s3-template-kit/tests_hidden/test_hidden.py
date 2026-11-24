import pytest
from r06s3pkg import FilterRegistry, TemplateEngine, parse_template


def test_nested_attribute_and_missing_value():
    engine = TemplateEngine()
    tpl = "{{ user.profile.title | default:'Guest' }} ({{ user.missing }})"
    assert engine.render(tpl, {"user": {"profile": {}}}) == "Guest ()"


def test_if_not_condition():
    engine = TemplateEngine()
    tpl = "{% if not locked %}OPEN{% else %}LOCKED{% endif %}"
    assert engine.render(tpl, {"locked": False}) == "OPEN"
    assert engine.render(tpl, {"locked": True}) == "LOCKED"


def test_unclosed_tag_raises_value_error():
    with pytest.raises(ValueError):
        parse_template("{% if flag %}hello")


def test_filter_numeric_arguments_truncate_and_add():
    engine = TemplateEngine()
    tpl = "{{ title | truncate:4 | upper }}:{{ count | add:10 }}:{{ price | add:1.5 }}"
    result = engine.render(tpl, {"title": "abcdef", "count": 5, "price": 2.0})
    assert result == "ABCD:15:3.5"


def test_filter_quoted_argument_containing_colons_and_pipes():
    engine = TemplateEngine()
    tpl = '{{ missing | default:"http://localhost:8080/a|b" }}'
    result = engine.render(tpl, {})
    assert result == "http://localhost:8080/a|b"


def test_filter_quoted_numeric_string_stays_string():
    reg = FilterRegistry()
    reg.register("type_tag", lambda v, arg: f"{type(arg).__name__}:{arg}")
    engine = TemplateEngine(filters=reg)
    assert engine.render('{{ x | type_tag:"42" }}', {"x": 1}) == "str:42"
    assert engine.render("{{ x | type_tag:42 }}", {"x": 1}) == "int:42"


def test_for_loop_does_not_leak_or_mutate_caller_context():
    engine = TemplateEngine()
    ctx = {"items": ["x", "y"]}
    tpl = "{% for item in items %}{{ item }}{% endfor %}[{{ item }}][{{ loop.index }}]"
    rendered = engine.render(tpl, ctx)
    assert rendered == "xy[][]"
    assert "item" not in ctx
    assert "loop" not in ctx


def test_for_loop_restores_shadowed_outer_variable():
    engine = TemplateEngine()
    ctx = {"item": "OUTER", "items": ["inner1", "inner2"]}
    tpl = "{{ item }}->{% for item in items %}{{ item }},{% endfor %}->{{ item }}"
    assert engine.render(tpl, ctx) == "OUTER->inner1,inner2,->OUTER"
    assert ctx["item"] == "OUTER"


def test_nested_for_loops_preserve_outer_loop_metadata():
    engine = TemplateEngine()
    ctx = {
        "groups": [
            {"name": "G1", "members": ["a", "b"]},
            {"name": "G2", "members": ["c"]},
        ]
    }
    tpl = (
        "{% for g in groups %}"
        "({{ loop.index }}:{{ g.name }}="
        "{% for m in g.members %}{{ loop.index }}{{ m }}{% endfor %}"
        "/{{ loop.index }}:{{ loop.last }})"
        "{% endfor %}"
    )
    assert engine.render(tpl, ctx) == "(1:G1=1a2b/1:False)(2:G2=1c/2:True)"
