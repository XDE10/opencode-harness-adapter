from __future__ import annotations

import ast
from pylintlet.analyzer import ScopeAnalyzer
from pylintlet.directives import Diagnostic, parse_suppressions


class LinterEngine:
    def __init__(self, enabled_codes: set[str] | None = None) -> None:
        self.enabled_codes = (
            {c.upper() for c in enabled_codes} if enabled_codes is not None else None
        )

    def lint_source(self, source: str) -> list[Diagnostic]:
        tree = ast.parse(source)
        suppressions = parse_suppressions(source)
        analyzer = ScopeAnalyzer()
        raw_diagnostics = analyzer.analyze(tree)

        results: list[Diagnostic] = []
        for diag in raw_diagnostics:
            if self.enabled_codes is not None and diag.code not in self.enabled_codes:
                continue
            if suppressions.is_suppressed(diag.line, diag.code):
                continue
            results.append(diag)
        return sorted(results)
