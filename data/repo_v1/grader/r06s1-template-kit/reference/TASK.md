# Issue Report: `r06s1pkg` Mini Template Engine Edge Cases

## Background
`r06s1pkg` is a lightweight template engine supporting variable interpolation (`{{ expr }}`), filter pipelines (`{{ val | filter1 | filter2:arg }}`), conditional blocks (`{% if [not] var %}...{% else %}...{% endif %}`), and loop blocks (`{% for item in items %}...{% endfor %}`).

## Reported Failures
We have observed two separate issues in production templates:

1. **Filter Arguments Containing Colons or Quotes**:
   - In `{{ expr | filter_name:arg }}`, a filter argument may itself contain colons (for example `{{ path | prefix:http://example.com }}` or `{{ ts | default:12:00:00 }}`) or be wrapped in matching single or double quotes (`{{ name | default:"N/A: none" }}` or `{{ items | join:", " }}`).
   - Currently, filter parsing corrupts arguments that contain additional `:` characters and fails to strip matching outer single/double quotes from quoted filter arguments.

2. **Loop Context Leakage & Shadowing in `{% for %}` Blocks**:
   - Rendering a `{% for item in items %}` block mutates the caller's context dictionary in-place and leaks both the loop variable (`item`) and `loop` metadata into the outer scope after `{% endfor %}`.
   - Furthermore, when a loop variable has the same name as an existing outer context variable (or inside nested `{% for %}` loops), the outer variable value (and outer `loop` metadata in nested loops) is overwritten instead of being restored when the inner loop finishes.

## Specification
1. **Filter Expression Parsing (`parser.py`)**:
   - A variable tag `{{ expr | f1 | f2:arg }}` splits filters on `|`.
   - Each filter segment has a filter name and an optional single string argument separated by the *first* `:` only (e.g. `prefix:http://example.com` -> filter name `"prefix"`, argument `"http://example.com"`).
   - After trimming surrounding whitespace from the argument, if the argument is at least 2 characters long and starts and ends with matching `"` or matching `'`, strip one pair of outer quotes (e.g. `", "` -> `", "`, `'12:00'` -> `12:00`).
   - Filters without `:` must have `arg=None`.

2. **Scoped Loop Execution (`renderer.py`)**:
   - `TemplateEngine.render(template_text, context)` must never mutate the caller-supplied `context` dictionary.
   - Inside `{% for var_name in iterable_expr %}`, `var_name` is bound to each item, and `loop` is bound to a dict `{"index": 1-based int, "index0": 0-based int, "first": bool, "last": bool, "length": int}`.
   - When the `{% for %}` block exits, any prior values for `var_name` and `loop` from the enclosing scope must be restored (or removed if they were not present in the enclosing scope).
