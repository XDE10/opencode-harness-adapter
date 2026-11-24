from __future__ import annotations

import re
from dataclasses import dataclass, field


class TemplateSyntaxError(ValueError):
    pass


class Node:
    pass


@dataclass
class TextNode(Node):
    text: str


@dataclass
class VarNode(Node):
    var_path: str
    filters: list[tuple[str, str | None]] = field(default_factory=list)


@dataclass
class IfNode(Node):
    var_path: str
    negate: bool
    true_branch: list[Node]
    false_branch: list[Node]


@dataclass
class ForNode(Node):
    item_var: str
    iterable_path: str
    body: list[Node]


TOKEN_RE = re.compile(r"(\{\{.*?\}\}|\{%.*?%\})", re.DOTALL)


def _parse_var_tag(raw_inner: str) -> VarNode:
    parts = [p.strip() for p in raw_inner.split("|")]
    if not parts or not parts[0]:
        raise TemplateSyntaxError("Empty variable expression")
    var_path = parts[0]
    filters: list[tuple[str, str | None]] = []
    for raw_filter in parts[1:]:
        if not raw_filter:
            raise TemplateSyntaxError(f"Malformed filter in '{raw_inner}'")
        if ":" in raw_filter:
            pieces = raw_filter.split(":")
            fname = pieces[0].strip()
            farg = pieces[1].strip()
            filters.append((fname, farg))
        else:
            filters.append((raw_filter.strip(), None))
    return VarNode(var_path=var_path, filters=filters)


def parse_template(template_text: str) -> list[Node]:
    tokens = TOKEN_RE.split(template_text)
    root: list[Node] = []
    stack: list[tuple[str, Node, list[Node]]] = []
    current_list = root

    for tok in tokens:
        if not tok:
            continue
        if tok.startswith("{{") and tok.endswith("}}"):
            inner = tok[2:-2].strip()
            current_list.append(_parse_var_tag(inner))
        elif tok.startswith("{%") and tok.endswith("%}"):
            inner = tok[2:-2].strip()
            words = inner.split()
            if not words:
                raise TemplateSyntaxError("Empty block tag")
            tag = words[0]
            if tag == "if":
                if len(words) == 2:
                    negate, cond_path = False, words[1]
                elif len(words) == 3 and words[1] == "not":
                    negate, cond_path = True, words[2]
                else:
                    raise TemplateSyntaxError(f"Invalid if tag: {inner}")
                node = IfNode(var_path=cond_path, negate=negate, true_branch=[], false_branch=[])
                current_list.append(node)
                stack.append(("if", node, current_list))
                current_list = node.true_branch
            elif tag == "else":
                if not stack or stack[-1][0] != "if":
                    raise TemplateSyntaxError("Unexpected {% else %}")
                _, if_node, _ = stack[-1]
                assert isinstance(if_node, IfNode)
                current_list = if_node.false_branch
            elif tag == "endif":
                if not stack or stack[-1][0] != "if":
                    raise TemplateSyntaxError("Unexpected {% endif %}")
                _, _, parent_list = stack.pop()
                current_list = parent_list
            elif tag == "for":
                if len(words) != 4 or words[2] != "in":
                    raise TemplateSyntaxError(f"Invalid for tag: {inner}")
                node = ForNode(item_var=words[1], iterable_path=words[3], body=[])
                current_list.append(node)
                stack.append(("for", node, current_list))
                current_list = node.body
            elif tag == "endfor":
                if not stack or stack[-1][0] != "for":
                    raise TemplateSyntaxError("Unexpected {% endfor %}")
                _, _, parent_list = stack.pop()
                current_list = parent_list
            else:
                raise TemplateSyntaxError(f"Unknown block tag: {tag}")
        else:
            current_list.append(TextNode(text=tok))

    if stack:
        unclosed = stack[-1][0]
        raise TemplateSyntaxError(f"Unclosed block tag: {unclosed}")

    return root
