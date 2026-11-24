from __future__ import annotations

from typing import Any

from r06s1pkg.filters import FilterRegistry
from r06s1pkg.parser import (
    ForNode,
    IfNode,
    Node,
    TemplateSyntaxError,
    TextNode,
    VarNode,
    parse_template,
)


def resolve_path(context: dict[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return ""
            current = current[part]
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return ""
    return current


class TemplateEngine:
    def __init__(self, filters: FilterRegistry | None = None) -> None:
        self.filters = filters if filters is not None else FilterRegistry()

    def render(self, template_text: str, context: dict[str, Any] | None = None) -> str:
        nodes = parse_template(template_text)
        active_ctx = context if context is not None else {}
        return self._render_nodes(nodes, active_ctx)

    def _render_nodes(self, nodes: list[Node], context: dict[str, Any]) -> str:
        out: list[str] = []
        for node in nodes:
            if isinstance(node, TextNode):
                out.append(node.text)
            elif isinstance(node, VarNode):
                val = resolve_path(context, node.var_path)
                for fname, farg in node.filters:
                    val = self.filters.apply(fname, val, farg)
                out.append("" if val is None else str(val))
            elif isinstance(node, IfNode):
                raw_val = resolve_path(context, node.var_path)
                truthy = bool(raw_val)
                if node.negate:
                    truthy = not truthy
                branch = node.true_branch if truthy else node.false_branch
                out.append(self._render_nodes(branch, context))
            elif isinstance(node, ForNode):
                iterable = resolve_path(context, node.iterable_path)
                if not iterable or not hasattr(iterable, "__iter__"):
                    continue
                items = list(iterable)
                total = len(items)
                for idx, item in enumerate(items):
                    context[node.item_var] = item
                    context["loop"] = {
                        "index": idx + 1,
                        "index0": idx,
                        "first": idx == 0,
                        "last": idx == total - 1,
                        "length": total,
                    }
                    out.append(self._render_nodes(node.body, context))
        return "".join(out)
