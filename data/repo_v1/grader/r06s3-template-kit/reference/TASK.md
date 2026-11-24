# Issue Report: `r06s3pkg` Template Engine Filter Argument Parsing & Scoped Loop Context Leaks

## Background
`r06s3pkg` is a lightweight template rendering engine supporting variable interpolation (`{{ expr | filter:arg }}`), conditional blocks (`{% if cond %}...{% else %}...{% endif %}`), and loop blocks (`{% for item in items %}...{% endfor %}`).

Recent bug reports have flagged two regressions during template parsing and stateful context execution:
1. **Filter argument parsing with colons or numeric types**: When a filter argument inside `{{ var | filter:arg }}` contains a quoted string with colons (e.g. `{{ name | default:"N/A:None" }}`) or an integer/float argument (e.g. `{{ text | truncate:5 }}`), parsing either splits the argument incorrectly on inner colons or leaves numeric arguments as raw strings, breaking filters in `FilterRegistry` that expect typed arguments (or unquoted/quoted strings preserved intact).
2. **Loop context variable leakage and outer variable corruption**: When executing `{% for x in seq %}` blocks (including nested loops or loops that shadow an outer context variable), the renderer mutates the shared context dictionary directly and does not isolate/restore outer variables or `loop` metadata (`loop.index`, `loop.first`, `loop.last`) after the loop finishes or across outer/inner loop boundaries.

## Behavioral Specification

### 1. Expression & Filter Parsing (`src/r06s3pkg/parser.py`)
- Variable tags have the form `{{ expr }}` where `expr` is a dotted variable path followed by zero or more pipe-separated filters:
  `var_path | filter1 | filter2:arg2`
- **Pipe splitting**: Filter stages are separated by `|` outside of double-quoted or single-quoted string literals.
- **Filter name & argument parsing**:
  - A filter token has an optional argument separated by the **first** `:` (`name:raw_arg`). Any subsequent `:` characters belong to `raw_arg` (e.g., `default:"a:b:c"` has filter name `"default"` and argument `"a:b:c"`).
  - If `raw_arg` is enclosed in matching double quotes (`"..."`) or single quotes (`'...'`), strip the outer quotes and return the inner string as a `str` (even if the inner content looks like a number).
  - If `raw_arg` is unquoted:
    - If it parses as an integer (`int`), coerce it to `int` (e.g., `truncate:5` -> `5`).
    - Else if it parses as a float (`float`), coerce it to `float`.
    - Otherwise return the stripped `str`.
  - If no `:` is present, the filter argument is `None`.

### 2. Stateful Context & Block Rendering (`src/r06s3pkg/renderer.py`)
- **Variable resolution**:
  - Dotted paths like `user.name` resolve across nested `dict` objects and object attributes.
  - Missing keys or attributes resolve to `None`.
- **`{% for item in collection %}` execution**:
  - Within each iteration of a `for` loop, the loop target variable (`item`) and a `loop` metadata dict (`{"index": 1-based int, "index0": 0-based int, "first": bool, "last": bool, "length": int}`) must be bound in the current scope.
  - **Scope isolation**:
    - After a `{% for %}` loop finishes, any outer variable that had the same name as `item` (or `loop`) before the loop entered MUST be restored to its pre-loop value.
    - If `item` (or `loop`) did not exist in the scope before the loop, it MUST NOT remain defined after `{% endfor %}`.
    - In nested `{% for %}` loops, once the inner loop finishes, the outer loop's `loop` metadata (`loop.index`, `loop.last`, etc.) and outer loop variable must remain intact for the remainder of the outer loop body.
    - The caller's original `context` dictionary passed into `TemplateEngine.render(template, context)` must never be mutated in-place.
