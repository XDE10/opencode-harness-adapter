import re
from dataclasses import dataclass, field
from r06s2pkg.filters import FilterSpec

TOKEN_RE = re.compile(r"(\{\{.*?\}\}|\{%.*?%\})", re.DOTALL)


class Node:
    pass


@dataclass
class TextNode(Node):
    text: str


@dataclass
class VarNode(Node):
    path: str
    filters: list[FilterSpec] = field(default_factory=list)


@dataclass
class IfNode(Node):
    condition: VarNode
    true_branch: list[Node] = field(default_factory=list)
    false_branch: list[Node] = field(default_factory=list)


@dataclass
class ForNode(Node):
    var_name: str
    iterable_expr: VarNode
    body: list[Node] = field(default_factory=list)


def parse_expression(raw: str) -> VarNode:
    parts = [p.strip() for p in raw.strip().split("|") if p.strip()]
    if not parts:
        raise ValueError("Empty template expression")
    path = parts[0]
    filters: list[FilterSpec] = []
    for segment in parts[1:]:
        if ":" in segment:
            name, arg = segment.split(":", 1)
            arg = arg.strip()
            if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in ("'", '"'):
                arg = arg[1:-1]
            filters.append(FilterSpec(name=name.strip(), arg=arg))
        else:
            filters.append(FilterSpec(name=segment.strip(), arg=None))
    return VarNode(path=path, filters=filters)


def parse_template(source: str) -> list[Node]:
    tokens = TOKEN_RE.split(source)
    root: list[Node] = []
    stack: list[tuple[str, Node, list[Node]]] = [("root", Node(), root)]

    for token in tokens:
        if not token:
            continue
        current_list = stack[-1][2]
        if token.startswith("{{") and token.endswith("}}"):
            expr = token[2:-2].strip()
            current_list.append(parse_expression(expr))
        elif token.startswith("{%") and token.endswith("%}"):
            stmt = token[2:-2].strip()
            if stmt.startswith("if "):
                cond_expr = parse_expression(stmt[3:].strip())
                node = IfNode(condition=cond_expr)
                current_list.append(node)
                stack.append(("if", node, node.true_branch))
            elif stmt == "else":
                tag, node, _ = stack[-1]
                if tag != "if" or not isinstance(node, IfNode):
                    raise SyntaxError("Unexpected {% else %}")
                stack[-1] = ("if_else", node, node.false_branch)
            elif stmt == "endif":
                tag, _, _ = stack.pop()
                if tag not in ("if", "if_else"):
                    raise SyntaxError("Unmatched {% endif %}")
            elif stmt.startswith("for "):
                rest = stmt[4:].strip()
                if " in " not in rest:
                    raise SyntaxError("Invalid {% for %} syntax")
                var_name, iter_raw = rest.split(" in ", 1)
                node = ForNode(
                    var_name=var_name.strip(),
                    iterable_expr=parse_expression(iter_raw.strip()),
                )
                current_list.append(node)
                stack.append(("for", node, node.body))
            elif stmt == "endfor":
                tag, _, _ = stack.pop()
                if tag != "for":
                    raise SyntaxError("Unmatched {% endfor %}")
            else:
                raise SyntaxError(f"Unknown statement: {stmt}")
        else:
            current_list.append(TextNode(text=token))

    if len(stack) != 1:
        raise SyntaxError("Unclosed block tag in template")
    return root
