from __future__ import annotations

from collections.abc import Collection

from r15s2lint.directives import Diagnostic, parse_noqa_map
from r15s2lint.scope import analyze_ast


class LintEngine:
    """Runs AST scope checks and filters diagnostics through noqa and query rules."""

    DEFAULT_RULES: frozenset[str] = frozenset({"L101", "L102", "L103"})

    def __init__(self, default_rules: Collection[str] | None = None) -> None:
        if default_rules is None:
            self.default_rules = set(self.DEFAULT_RULES)
        else:
            self.default_rules = {r.upper() for r in default_rules}

    def lint_source(
        self,
        source: str,
        enabled_rules: Collection[str] | None = None,
    ) -> list[Diagnostic]:
        active_rules = (
            self.default_rules
            if enabled_rules is None
            else {r.upper() for r in enabled_rules}
        )
        tracker = analyze_ast(source)
        suppressions = parse_noqa_map(source)

        raw_diagnostics: list[Diagnostic] = []

        for binding in tracker.imports.values():
            if not binding.used:
                raw_diagnostics.append(
                    Diagnostic(
                        line=binding.line,
                        code="L101",
                        message=f"Unused import '{binding.name}'",
                        symbol=binding.name,
                    )
                )

        for line, name in tracker.shadow_events:
            raw_diagnostics.append(
                Diagnostic(
                    line=line,
                    code="L102",
                    message=f"Local '{name}' shadows imported '{name}'",
                    symbol=name,
                )
            )

        for line in tracker.bare_except_lines:
            raw_diagnostics.append(
                Diagnostic(
                    line=line,
                    code="L103",
                    message="Bare 'except:' clause is not allowed",
                    symbol="except",
                )
            )

        filtered: list[Diagnostic] = []
        for diag in raw_diagnostics:
            if diag.code not in active_rules:
                continue
            if suppressions.is_suppressed(diag.line, diag.code):
                continue
            filtered.append(diag)

        return sorted(filtered)


def lint_code(
    source: str,
    enabled_rules: Collection[str] | None = None,
) -> list[Diagnostic]:
    return LintEngine().lint_source(source, enabled_rules=enabled_rules)
