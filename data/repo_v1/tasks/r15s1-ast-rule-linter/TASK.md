# Issue Report: Incorrect `# noqa` suppression parsing and nested-scope import shadowing in `pylintlet`

## Context
`pylintlet` is our lightweight AST-based Python micro-linter. It parses source files for inline `# noqa` directives, walks the AST to track lexical scopes and unused imports (`L101`) or mutable default arguments (`L102`), and filters/reports sorted diagnostics.

Users have reported two separate regressions in production:

1. **Inline `# noqa` directives with trailing explanatory comments or whitespace fail to suppress specific rule codes:**
   Developers routinely write `# noqa: L101 -- imported for side effects` or `# noqa: L101, L102 # legacy` or `# noqa: l101`. Currently, `SuppressionMap` in `directives.py` fails to normalize or strip trailing text/comments after the rule code list, causing targeted suppressions to fail whenever extra commentary or lowercase codes are present.
2. **Function/comprehension parameters and local assignments in nested scopes are not properly isolated from module-level unused import tracking (`L101`):**
   In `analyzer.py`, `ScopeAnalyzer` tracks imported bindings and variable references across scopes. When a nested function (or local assignment inside a function) defines a parameter or local variable with the same name as a top-level import (e.g., `import json` at module level, and `def dump(json): return str(json)`), referencing that local parameter inside the function falsely marks the shadowed module-level `json` import as "used", suppressing a genuine `L101` unused-import diagnostic. Conversely, reading a module-level import inside a function where it is *not* shadowed should still mark the module-level import as used.

---

## Behavioral Specification

### 1. Inline `# noqa` Directive Parsing (`pylintlet.directives`)
- `parse_suppressions(source: str) -> SuppressionMap` scans each 1-indexed line for `# noqa` comments (case-insensitive `# noqa`).
- A blanket `# noqa` (or `# noqa` followed immediately by `-- ...` or `# ...` without a colon `:`) suppresses **all** rules on that line (`None` in the map for that line).
- A targeted `# noqa: <codes>` directive starts with `# noqa:` (case-insensitive) followed by a comma-separated list of rule codes.
  - Each rule code token starts with alphanumeric characters (e.g. `L101`, `l102`).
  - Any trailing comment or explanation on the line after the code list—such as `-- reason`, `# comment`, or whitespace-separated explanation tokens after a code (e.g., `# noqa: L101, L102 -- needed for API`)—must be ignored rather than polluting the parsed code token.
  - All parsed rule codes must be normalized to uppercase (e.g. `l101` -> `L101`).
- `SuppressionMap.is_suppressed(line: int, code: str) -> bool` returns `True` if `line` has a blanket suppression or if `code.upper()` is in the line's targeted suppression set.

### 2. Scope & Import Tracking (`pylintlet.analyzer` & `pylintlet.engine`)
- **Rule `L101` (Unused Import):**
  - Any `import foo` (bound name `foo`, or `import foo.bar` bound name `foo`, or `import foo as f` bound name `f`) and `from pkg import bar` (bound name `bar`, or `as b` bound name `b`) introduces an import binding in the current scope. (`from pkg import *` is ignored).
  - A `Name` with `ast.Load()` context resolves to the **innermost enclosing scope** that defines that name (either as a function argument, local assignment/target, exception handler name, or import in that scope).
  - If a function defines a parameter or local variable (via `arg`, `Assign`, `AnnAssign`, `AugAssign`, `For`, `NamedExpr`) with name `x`, any `Load` of `x` inside that function's scope resolves to the local binding `x`, **not** to an outer/module-level import named `x`.
  - However, a default argument expression in `def fn(x=json.dumps):` is evaluated in the **enclosing** scope, not the function's own body scope!
  - Every import binding that is never resolved by a `Load` in its defining scope or an unshadowed inner scope must emit a `Diagnostic(line=node.lineno, col=node.col_offset, code="L101", message=f"Unused import '{bound_name}'")`.
- **Rule `L102` (Mutable Default Argument):**
  - Any `FunctionDef` or `AsyncFunctionDef` whose positional or keyword-only default argument value is a literal `ast.List`, `ast.Dict`, or `ast.Set` emits a `Diagnostic(line=default_node.lineno, col=default_node.col_offset, code="L102", message="Mutable default argument")`.
- **Engine (`LinterEngine.lint_source(source: str)`):**
  - Runs the AST analyzer, filters out diagnostics where `suppressions.is_suppressed(diag.line, diag.code)` is `True` (as well as filtered by `enabled_codes` if configured), and returns diagnostics sorted by `(line, col, code)`.
