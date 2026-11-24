from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class ImportBinding:
    name: str
    line: int
    used: bool = False


@dataclass
class ScopeFrame:
    kind: str
    local_defs: dict[str, int] = field(default_factory=dict)
    used_names: set[str] = field(default_factory=set)


class ScopeTracker(ast.NodeVisitor):
    """Visits an AST to track root imports, nested scope usages, and shadowing."""

    def __init__(self) -> None:
        self.imports: dict[str, ImportBinding] = {}
        self.frames: list[ScopeFrame] = [ScopeFrame(kind="module")]
        self.shadow_events: list[tuple[int, str]] = []
        self.bare_except_lines: list[int] = []

    @property
    def current_frame(self) -> ScopeFrame:
        return self.frames[-1]

    def push_scope(self, kind: str) -> None:
        self.frames.append(ScopeFrame(kind=kind))

    def pop_scope(self) -> None:
        child = self.frames.pop()
        parent = self.current_frame
        for name in child.used_names:
            parent.used_names.add(name)
            if name in self.imports:
                self.imports[name].used = True

    def record_import(self, name: str, line: int) -> None:
        if len(self.frames) == 1:
            self.imports[name] = ImportBinding(name=name, line=line, used=False)
        else:
            self.record_local_def(name, line)

    def record_local_def(self, name: str, line: int) -> None:
        frame = self.current_frame
        frame.local_defs.setdefault(name, line)
        if frame.kind != "module" and name in self.imports:
            self.shadow_events.append((line, name))
            self.imports.pop(name, None)

    def record_usage(self, name: str) -> None:
        self.current_frame.used_names.add(name)
        if len(self.frames) == 1 and name in self.imports:
            self.imports[name].used = True

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            bound = alias.asname if alias.asname else alias.name.split(".")[0]
            self.record_import(bound, node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name == "*":
                continue
            bound = alias.asname if alias.asname else alias.name
            self.record_import(bound, node.lineno)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        if len(self.frames) > 1:
            self.record_local_def(node.name, node.lineno)
        for dec in node.decorator_list:
            self.visit(dec)
        for default in node.args.defaults + node.args.kw_defaults:
            if default is not None:
                self.visit(default)

        self.push_scope("function")
        all_args = (
            list(node.args.posonlyargs)
            + list(node.args.args)
            + list(node.args.kwonlyargs)
        )
        if node.args.vararg:
            all_args.append(node.args.vararg)
        if node.args.kwarg:
            all_args.append(node.args.kwarg)
        for arg in all_args:
            self.record_local_def(arg.arg, arg.lineno)
        for stmt in node.body:
            self.visit(stmt)
        self.pop_scope()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if len(self.frames) > 1:
            self.record_local_def(node.name, node.lineno)
        for dec in node.decorator_list:
            self.visit(dec)
        for base in node.bases:
            self.visit(base)
        for kw in node.keywords:
            self.visit(kw)
        self.push_scope("class")
        for stmt in node.body:
            self.visit(stmt)
        self.pop_scope()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.record_local_def(node.id, node.lineno)
        elif isinstance(node.ctx, ast.Load):
            self.record_usage(node.id)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.bare_except_lines.append(node.lineno)
        else:
            self.visit(node.type)
        if node.name and len(self.frames) > 1:
            self.record_local_def(node.name, node.lineno)
        for stmt in node.body:
            self.visit(stmt)


def analyze_ast(source: str) -> ScopeTracker:
    tree = ast.parse(source)
    tracker = ScopeTracker()
    tracker.visit(tree)
    return tracker
