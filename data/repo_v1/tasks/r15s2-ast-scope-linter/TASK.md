# Issue Report: False Positives in Nested Scopes and Over-Broad Specific `# noqa` Suppressions

## Summary
Our Python AST micro-linter (`r15s2lint`) checks Python source files for unused imports (`L101`), variable shadowing of outer imports (`L102`), and bare `except:` blocks (`L103`). Two defects have surfaced in production linting pipelines:

1. **Nested Scope Import Tracking & Shadowing (`L101` / `L102`)**:
   - When an imported name is referenced inside a nested scope (such as a function body, comprehension, or class method) without being shadowed in that scope, it is sometimes still flagged as an unused import (`L101`), or outer bindings are corrupted when a nested function shadows a module-level import and then exits.
   - Specifically, when a child scope finishes (`pop_scope()`), any usage recorded in the child scope for a name that was **not** locally rebound in that child scope must propagate up as a usage of the enclosing scope's binding. However, if the child scope *did* locally rebind/shadow the name (e.g., via assignment or parameter definition), references in that child scope apply to the local binding—not the module-level import—and popping the child scope must roll back the local binding rather than overwriting the parent scope's import binding.

2. **Specific vs. Blanket `# noqa` Directive Conflict Resolution**:
   - `parse_noqa_map(source)` extracts inline `# noqa` comments per line and `LintEngine.lint_source()` filters diagnostics through `SuppressionIndex.is_suppressed(line, code)`.
   - A blanket `# noqa` (with no codes listed) should suppress **all** diagnostic codes on that line.
   - A targeted `# noqa: L101, L102` (case-insensitive codes, optional spaces around commas) should suppress **only** the listed codes (`L101` and `L102`) on that line, leaving other diagnostics on the same line (or adjacent lines) active.
   - Currently, targeted `# noqa: CODE` comments either suppress unrelated rules on the same line or fail to match normalized uppercase rule codes when parsed and queried across `directives.py` and `engine.py`.

## Expected Behavioral Specification

### Rules
- **`L101` (Unused Import)**: Emitted for each module-level imported binding name (`import foo` -> `foo`, `import foo.bar as fb` -> `fb`, `from pkg import bar` -> `bar`) that is never referenced in any scope where that import binding is visible. Line number is the import statement's `lineno`.
- **`L102` (Import Shadowed)**: Emitted when a function parameter or local assignment inside a function/class scope defines a name that shadows an active module-level import binding. Line number is the assignment target or function definition line where the shadowing binding occurs.
- **`L103` (Bare Except)**: Emitted for any `except:` handler where `handler.type is None`. Line number is the `ExceptHandler.lineno`.

### Scope & Rollback Rules (`ScopeTracker`)
- Module scope is the root scope.
- Pushing a function (`FunctionDef`, `AsyncFunctionDef`) or class (`ClassDef`) scope creates an isolated frame for local definitions and local usages.
- In a function scope, parameters (`args.posonlyargs`, `args.args`, `args.kwonlyargs`, `args.vararg`, `args.kwarg`) and assignment targets (`ast.Name` in `Store` context) count as local definitions. If a local definition inside a non-root scope has the same name as a root-scope import, record an `L102` shadowing event at that node's line.
- An `ast.Name` in `Load` context records a usage in the current scope.
- When popping a child scope back into its parent scope:
  - Only names that were **not** locally defined in the child scope have their usage propagated to the parent scope.
  - Names that **were** locally defined in the child scope do **not** mark the parent/root import as used, and must not overwrite or invalidate the parent scope's import record.

### Suppression & Query Composition (`SuppressionIndex` & `LintEngine`)
- Inline `# noqa` comments may appear anywhere in a line's comment text:
  - `# noqa` (not followed by `:`) suppresses all rules on that line (`None` / wildcard sentinel).
  - `# noqa: L101` or `# noqa: l101, L103` suppresses only the specified uppercase rule codes on that line. If additional trailing comment text follows after a space or `#` (e.g. `# noqa: L101 - intentional`), only the comma-separated rule codes (`[A-Za-z0-9_]+`) are extracted.
- `LintEngine.lint_source(source, enabled_rules=None)` returns a list of `Diagnostic` objects sorted by `(line, code, message)`. If `enabled_rules` is provided (a collection of rule codes), only diagnostics whose `code` is in `enabled_rules` and not suppressed by `# noqa` are returned.
