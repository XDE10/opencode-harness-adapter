from typing import Any
from r06s3pkg.filters import FilterRegistry
from r06s3pkg.parser import ForNode, IfNode, TextNode, VarNode, parse_template


def resolve_path(context: dict[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        else:
            if not hasattr(current, part):
                return None
            current = getattr(current, part)
    return current


class TemplateEngine:
    def __init__(self, filters: FilterRegistry | None = None) -> None:
        self.filters = filters if filters is not None else FilterRegistry()

    def render(self, template_source: str, context: dict[str, Any] | None = None) -> str:
        nodes = parse_template(template_source)
        ctx = context if context is not None else {}
        return self._render_nodes(nodes, ctx)

    def _render_nodes(self, nodes: list[Any], context: dict[str, Any]) -> str:
        out: list[str] = []
        for node in nodes:
            if isinstance(node, TextNode):
                out.append(node.text)
            elif isinstance(node, VarNode):
                val = resolve_path(context, node.var_name)
                for f_spec in node.filters:
                    val = self.filters.apply(f_spec.name, val, f_spec.arg)
                out.append("" if val is None else str(val))
            elif isinstance(node, IfNode):
                cond_val = bool(resolve_path(context, node.condition_var))
                if node.negated:
                    cond_val = not cond_val
                branch = node.true_branch if cond_val else node.false_branch
                out.append(self._render_nodes(branch, context))
            elif isinstance(node, ForNode):
                raw_iter = resolve_path(context, node.iterable_var)
                items = list(raw_iter) if raw_iter is not None else []
                total = len(items)
                for idx, item in enumerate(items):
                    context[node.loop_var] = item
                    context["loop"] = {
                        "index": idx + 1,
                        "index0": idx,
                        "first": idx == 0,
                        "last": idx == total - 1,
                        "length": total,
                    }
                    out.append(self._render_nodes(node.body, context))
        return "".join(out)
