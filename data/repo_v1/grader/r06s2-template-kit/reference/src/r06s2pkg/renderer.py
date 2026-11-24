from typing import Any
from r06s2pkg.filters import FilterRegistry
from r06s2pkg.parser import ForNode, IfNode, Node, TextNode, VarNode, parse_template

_MISSING = object()


class TemplateEngine:
    def __init__(self, registry: FilterRegistry | None = None) -> None:
        self.registry = registry if registry is not None else FilterRegistry()

    def resolve_path(self, path: str, context: dict[str, Any]) -> Any:
        current: Any = context
        for part in path.split("."):
            if isinstance(current, dict):
                if part not in current:
                    return ""
                current = current[part]
            else:
                if not hasattr(current, part):
                    return ""
                current = getattr(current, part)
        return current

    def evaluate_var(self, node: VarNode, context: dict[str, Any]) -> Any:
        raw_val = self.resolve_path(node.path, context)
        return self.registry.apply_pipeline(raw_val, node.filters)

    def render(self, template: str, context: dict[str, Any] | None = None) -> str:
        nodes = parse_template(template)
        working_ctx = dict(context) if context is not None else {}
        return self._render_nodes(nodes, working_ctx)

    def _render_nodes(self, nodes: list[Node], context: dict[str, Any]) -> str:
        out: list[str] = []
        for node in nodes:
            if isinstance(node, TextNode):
                out.append(node.text)
            elif isinstance(node, VarNode):
                val = self.evaluate_var(node, context)
                out.append("" if val is None else str(val))
            elif isinstance(node, IfNode):
                cond_val = self.evaluate_var(node.condition, context)
                branch = node.true_branch if bool(cond_val) else node.false_branch
                out.append(self._render_nodes(branch, context))
            elif isinstance(node, ForNode):
                iterable = self.evaluate_var(node.iterable_expr, context)
                if not iterable:
                    continue
                items = list(iterable)
                total = len(items)
                prev_var = context.get(node.var_name, _MISSING)
                prev_loop = context.get("loop", _MISSING)
                try:
                    for idx, item in enumerate(items, start=1):
                        context[node.var_name] = item
                        context["loop"] = {
                            "index": idx,
                            "first": idx == 1,
                            "last": idx == total,
                        }
                        out.append(self._render_nodes(node.body, context))
                finally:
                    if prev_var is _MISSING:
                        context.pop(node.var_name, None)
                    else:
                        context[node.var_name] = prev_var
                    if prev_loop is _MISSING:
                        context.pop("loop", None)
                    else:
                        context["loop"] = prev_loop
        return "".join(out)
