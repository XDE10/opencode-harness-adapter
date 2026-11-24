# Issue Report: `r06s2pkg` Template Engine Filter Chaining & Loop Scope Rollback

## Background
`r06s2pkg` is a lightweight template engine supporting variable interpolation (`{{ expr }}`), chained filters with optional arguments (`{{ var | filter1:arg | filter2 }}`), conditionals (`{% if var %}` ... `{% else %}` ... `{% endif %}`), and loops (`{% for item in items %}` ... `{% endfor %}`).

We discovered two separate regressions when templates compose multi-step filter pipelines and when `{% for %}` loops iterate over collections that conflict with outer context variables or encounter empty iterables.

## Expected Behavior & Specification

1. **Multi-Step Filter Composition (`{{ expr | f1:arg1 | f2:arg2 }}`)**:
   - A variable expression inside `{{ ... }}` consists of a dotted variable path followed by zero or more pipe-separated (`|`) filter calls.
   - Each filter segment has the form `name` or `name:arg`, where `arg` (if present) had surrounding single/double quotes stripped or is kept as a raw string.
   - Filters must be applied in strict left-to-right declaration order: the output of filter `i` becomes the first argument (`value`) of filter `i + 1`.
   - When a filter in the chain is registered with `invalidate_empty=True` (via `FilterRegistry.register(name, fn, invalidate_empty=True)`) and the incoming value is `None` or `""`, that filter must short-circuit and evaluate to `""` without invoking `fn`, while subsequent filters in the chain still run on the resulting `""` unless they also short-circuit.
   - All parsed filters in the pipeline must be preserved in order by `parse_expression` and executed sequentially by `FilterRegistry.apply_pipeline`.

2. **Context Scoping, Loop Conflict Resolution, and Rollback (`{% for item in items %}`)**:
   - Entering a `{% for var_name in list_expr %}` block must isolate loop variable bindings from the outer context.
   - During each iteration, `var_name` is bound to the current element and `loop` is bound to a dict `{"index": 1-based index, "first": bool, "last": bool}`.
   - If `var_name` (or `loop`) already existed in the outer context before the `{% for %}` loop ran, the outer value must be restored (rolled back) after the loop completes.
   - If `var_name` (or `loop`) did **not** exist in the outer context before the loop, it must be removed from the context after the loop completes so it does not leak into subsequent template nodes.
   - Additionally, caller-supplied `context` dictionaries passed into `TemplateEngine.render(template, context)` must never be mutated in-place.

3. **Conditionals & Dotted Path Resolution**:
   - Dotted paths like `user.profile.name` resolve dictionary keys or object attributes at each step. Missing keys/attributes resolve to `""`.
   - `{% if cond %}` supports an optional `{% else %}` branch and evaluates standard Python truthiness of the resolved `cond` expression after any filters in `cond` are applied.
