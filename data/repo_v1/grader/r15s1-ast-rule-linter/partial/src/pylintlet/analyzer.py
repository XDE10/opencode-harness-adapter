from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pylintlet.directives import Diagnostic


@dataclass
class ImportBinding:
    name: str
    line: int
    col: int
    used: bool = False


@dataclass
class LexicalScope:
    imports: dict[str, ImportBinding] = field(default_factory=dict)
    locals: set[str] = field(default_factory=set)
    references: set[str] = field(default_factory=set)
    children: list[LexicalScope] = field(default_factory=list)


class ScopeAnalyzer(ast.NodeVisitor):
    def __init__(self) -> None:
        self.root_scope = LexicalScope()
        self._scope_stack: list[LexicalScope] = [self.root_scope]
        self.diagnostics: list[Diagnostic] = []

    @property
    def current_scope(self) -> LexicalScope:
        return self._scope_stack[-1]

    def analyze(self, tree: ast.AST) -> list[Diagnostic]:
        self.visit(tree)
        self._collect_unused_imports(self.root_scope)
        return sorted(self.diagnostics)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound = alias.asname if alias.asname else alias.name.split(".")[0]
            self.current_scope.imports[bound] = ImportBinding(
                name=bound, line=node.lineno, col=node.col_offset
            )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                continue
            bound = alias.asname if alias.asname else alias.name
            self.current_scope.imports[bound] = ImportBinding(
                name=bound, line=node.lineno, col=node.col_offset
            )

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.current_scope.locals.add(node.name)
        all_defaults = list(node.args.defaults) + [
            d for d in node.args.kw_defaults if d is not None
        ]
        for default_node in all_defaults:
            if isinstance(default_node, (ast.List, ast.Dict, ast.Set)):
                self.diagnostics.append(
                    Diagnostic(
                        line=default_node.lineno,
                        col=default_node.col_offset,
                        code="L102",
                        message="Mutable default argument",
                    )
                )
            self.visit(default_node)

        for dec in node.decorator_list:
            self.visit(dec)

        child_scope = LexicalScope()
        self.current_scope.children.append(child_scope)
        self._scope_stack.append(child_scope)
        for arg in (
            node.args.posonlyargs
            + node.args.args
            + node.args.kwonlyargs
            + ([node.args.vararg] if node.args.vararg else [])
            + ([node.args.kwarg] if node.args.kwarg else [])
        ):
            self.current_scope.locals.add(arg.arg)
        for stmt in node.body:
            self.visit(stmt)
        self._scope_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.current_scope.locals.add(node.id)
        elif isinstance(node.ctx, ast.Load):
            self.current_scope.references.add(node.id)
            for scope in reversed(self._scope_stack):
                if node.id in scope.imports:
                    scope.imports[node.id].used = True
                    break

    def _collect_unused_imports(self, scope: LexicalScope) -> None:
        for binding in scope.imports.values():
            if not binding.used:
                self.diagnostics.append(
                    Diagnostic(
                        line=binding.line,
                        col=binding.col,
                        code="L101",
                        message=f"Unused import '{binding.name}'",
                    )
                )
        for child in scope.children:
            self._collect_unused_imports(child)
