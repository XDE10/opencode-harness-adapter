import pytest
from r06s2pkg import FilterRegistry, TemplateEngine, parse_expression


def test_dotted_path_and_object_attribute_resolution() -> None:
    class Profile:
        def __init__(self, role: str) -> None:
            self.role = role

    engine = TemplateEngine()
    ctx = {"user": {"name": "dana", "profile": Profile("staff")}}
    out = engine.render("{{ user.name | upper }} ({{ user.profile.role }})", ctx)
    assert out == "DANA (staff)"


def test_missing_path_resolves_to_empty_string() -> None:
    engine = TemplateEngine()
    assert engine.render("[{{ user.missing.deep }}]", {"user": {}}) == "[]"


def test_syntax_errors_on_malformed_blocks() -> None:
    engine = TemplateEngine()
    with pytest.raises(SyntaxError):
        engine.render("{% if a %}hello", {"a": True})
    with pytest.raises(SyntaxError):
        engine.render("{% else %}", {})


def test_multi_step_filter_pipeline_execution_order() -> None:
    engine = TemplateEngine()
    tpl = "{{ slug | strip | prefix:'pre-' | suffix:'-post' | upper }}"
    assert engine.render(tpl, {"slug": "  core  "}) == "PRE-CORE-POST"

    expr = parse_expression("slug | prefix:'a' | suffix:'b'")
    assert [f.name for f in expr.filters] == ["prefix", "suffix"]


def test_filter_pipeline_empty_invalidation_recovery_via_default() -> None:
    engine = TemplateEngine()
    tpl = "{{ missing_var | upper | default:'fallback' | prefix:'[' | suffix:']' }}"
    assert engine.render(tpl, {}) == "[fallback]"


def test_filter_pipeline_chained_replacements_order_sensitive() -> None:
    engine = TemplateEngine()
    tpl = "{{ code | replace:'a->b' | replace:'b->c' }}"
    assert engine.render(tpl, {"code": "a_b"}) == "c_c"


def test_for_loop_restores_shadowed_outer_variable_and_loop_meta() -> None:
    engine = TemplateEngine()
    tpl = (
        "Before:{{ item }}|{% for item in list %}"
        "({{ loop.index }}:{{ item }})"
        "{% endfor %}|After:{{ item }}"
    )
    ctx = {"item": "OUTER", "list": ["x", "y"]}
    assert engine.render(tpl, ctx) == "Before:OUTER|(1:x)(2:y)|After:OUTER"


def test_nested_for_loops_rollback_outer_loop_metadata_and_var() -> None:
    engine = TemplateEngine()
    tpl = (
        "{% for x in rows %}"
        "[{{ loop.index }}:{{ x }}->"
        "{% for x in cols %}{{ loop.index }}{{ x }}{% endfor %}"
        ":{{ loop.index }}:{{ x }}]"
        "{% endfor %}"
    )
    ctx = {"rows": ["R1", "R2"], "cols": ["a", "b"]}
    assert engine.render(tpl, ctx) == "[1:R1->1a2b:1:R1][2:R2->1a2b:2:R2]"


def test_render_does_not_leak_loop_vars_or_mutate_caller_context() -> None:
    engine = TemplateEngine()
    caller_ctx = {"items": ["one", "two"]}
    tpl = "{% for entry in items %}{{ entry }}{% endfor %}|After:{{ entry }}|Loop:{{ loop.index }}"
    out = engine.render(tpl, caller_ctx)
    assert out == "onetwo|After:|Loop:"
    assert caller_ctx == {"items": ["one", "two"]}
