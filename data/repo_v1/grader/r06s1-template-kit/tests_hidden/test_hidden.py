import pytest
from r06s1pkg import FilterRegistry, TemplateEngine, TemplateSyntaxError


def test_chained_filters_and_negated_if():
    engine = TemplateEngine()
    tpl = "{% if not missing %}{{ title | strip | upper | suffix:! }}{% endif %}"
    assert engine.render(tpl, {"title": "  hello world  "}) == "HELLO WORLD!"


def test_custom_filter_registration():
    registry = FilterRegistry()
    registry.register("repeat", lambda val, count="2": str(val) * int(count))
    engine = TemplateEngine(filters=registry)
    assert engine.render("{{ word | repeat:3 }}", {"word": "ha"}) == "hahaha"


def test_syntax_error_on_unclosed_tag():
    engine = TemplateEngine()
    with pytest.raises(TemplateSyntaxError):
        engine.render("{% if flag %}hello", {"flag": True})


def test_filter_argument_with_colons():
    engine = TemplateEngine()
    tpl = "{{ slug | prefix:https://example.com:8443/ }}|{{ time | default:12:30:00 }}"
    result = engine.render(tpl, {"slug": "api/v1", "time": ""})
    assert result == "https://example.com:8443/api/v1|12:30:00"


def test_filter_argument_strips_matching_quotes():
    engine = TemplateEngine()
    tpl = '{{ items | join:", " }} / {{ empty_val | default:\'N/A: none\' }}'
    result = engine.render(tpl, {"items": ["a", "b", "c"], "empty_val": ""})
    assert result == "a, b, c / N/A: none"


def test_for_loop_does_not_mutate_caller_context_or_leak():
    engine = TemplateEngine()
    ctx = {"items": ["x", "y"]}
    tpl = "{% for item in items %}{{ item }}{% endfor %}[{{ item }}][{{ loop.index }}]"
    rendered = engine.render(tpl, ctx)
    assert rendered == "xy[][]"
    assert ctx == {"items": ["x", "y"]}


def test_for_loop_restores_shadowed_outer_variable():
    engine = TemplateEngine()
    ctx = {"item": "OUTER", "items": ["inner1", "inner2"]}
    tpl = "{{ item }}:{% for item in items %}{{ item }},{% endfor %}:{{ item }}"
    rendered = engine.render(tpl, ctx)
    assert rendered == "OUTER:inner1,inner2,:OUTER"
    assert ctx == {"item": "OUTER", "items": ["inner1", "inner2"]}


def test_nested_for_loops_restore_outer_loop_metadata_and_var():
    engine = TemplateEngine()
    ctx = {
        "groups": [
            {"members": ["a", "b"]},
            {"members": ["c"]},
        ]
    }
    tpl = (
        "{% for g in groups %}"
        "G{{ loop.index }}("
        "{% for g in g.members %}{{ g }}{{ loop.index }}{% endfor %}"
        ")={{ loop.index }};"
        "{% endfor %}"
    )
    assert engine.render(tpl, ctx) == "G1(a1b2)=1;G2(c1)=2;"
