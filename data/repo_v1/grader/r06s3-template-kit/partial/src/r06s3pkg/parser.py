from dataclasses import dataclass, field
import re
from typing import Any

TOKEN_RE = re.compile(r"(\{\{.*?\}\}|\{%.*?%\})", re.DOTALL)


@dataclass
class TextNode:
    text: str


@dataclass
class FilterSpec:
    name: str
    arg: Any = None


@dataclass
class VarNode:
    var_name: str
    filters: list[FilterSpec] = field(default_factory=list)


@dataclass
class IfNode:
    condition_var: str
    negated: bool
    true_branch: list[Any] = field(default_factory=list)
    false_branch: list[Any] = field(default_factory=list)


@dataclass
class ForNode:
    loop_var: str
    iterable_var: str
    body: list[Any] = field(default_factory=list)


def _split_outside_quotes(expr: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote_char: str | None = None
    for ch in expr:
        if quote_char is not None:
            current.append(ch)
            if ch == quote_char:
                quote_char = None
        else:
            if ch in ('"', "'"):
                quote_char = ch
                current.append(ch)
            elif ch == delimiter:
                parts.append("".join(current))
                current = []
            else:
                current.append(ch)
    parts.append("".join(current))
    return parts


def _parse_filter_arg(raw_arg: str) -> Any:
    s = raw_arg.strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def parse_var_expression(expr: str) -> VarNode:
    parts = [p.strip() for p in _split_outside_quotes(expr, "|")]
    var_name = parts[0]
    filters: list[FilterSpec] = []
    for raw_filter in parts[1:]:
        if not raw_filter:
            continue
        if ":" in raw_filter:
            f_name, raw_arg = raw_filter.split(":", 1)
            filters.append(FilterSpec(name=f_name.strip(), arg=_parse_filter_arg(raw_arg)))
        else:
            filters.append(FilterSpec(name=raw_filter.strip(), arg=None))
    return VarNode(var_name=var_name, filters=filters)


def parse_template(source: str) -> list[Any]:
    tokens = TOKEN_RE.split(source)
    root: list[Any] = []
    stack: list[tuple[str, Any, list[Any]]] = [("root", None, root)]

    for token in tokens:
        if not token:
            continue
        if token.startswith("{{") and token.endswith("}}"):
            inner = token[2:-2].strip()
            stack[-1][2].append(parse_var_expression(inner))
        elif token.startswith("{%") and token.endswith("%}"):
            tag = token[2:-2].strip()
            words = tag.split()
            if not words:
                continue
            kw = words[0]
            if kw == "if":
                negated = len(words) >= 3 and words[1] == "not"
                cond_var = words[2] if negated else words[1]
                node = IfNode(condition_var=cond_var, negated=negated)
                stack[-1][2].append(node)
                stack.append(("if", node, node.true_branch))
            elif kw == "else":
                if stack[-1][0] != "if":
                    raise ValueError("Unexpected {% else %}")
                if_node = stack[-1][1]
                stack[-1] = ("else", if_node, if_node.false_branch)
            elif kw == "endif":
                if stack[-1][0] not in ("if", "else"):
                    raise ValueError("Unexpected {% endif %}")
                stack.pop()
            elif kw == "for":
                if len(words) != 4 or words[2] != "in":
                    raise ValueError(f"Malformed for tag: {tag}")
                for_node = ForNode(loop_var=words[1], iterable_var=words[3])
                stack[-1][2].append(for_node)
                stack.append(("for", for_node, for_node.body))
            elif kw == "endfor":
                if stack[-1][0] != "for":
                    raise ValueError("Unexpected {% endfor %}")
                stack.pop()
            else:
                raise ValueError(f"Unknown template tag: {kw}")
        else:
            stack[-1][2].append(TextNode(text=token))

    if len(stack) != 1:
        raise ValueError(f"Unclosed block tag: {stack[-1][0]}")
    return root
