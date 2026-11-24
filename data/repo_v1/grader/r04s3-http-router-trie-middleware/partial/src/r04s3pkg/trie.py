from dataclasses import dataclass, field
from typing import Any

from r04s3pkg.models import Handler, Middleware, SegmentSpec


def parse_pattern(pattern: str) -> list[SegmentSpec]:
    cleaned = pattern.strip("/")
    if not cleaned:
        return []
    specs: list[SegmentSpec] = []
    for part in cleaned.split("/"):
        if part.startswith("{") and part.endswith("}"):
            inner = part[1:-1]
            is_star = inner.startswith("*")
            if is_star:
                inner = inner[1:]
            if ":" in inner:
                name, ptype = inner.split(":", 1)
            else:
                name, ptype = inner, ("path" if is_star else "str")
            kind = "wildcard" if (is_star or ptype == "path") else "param"
            specs.append(SegmentSpec(raw=part, kind=kind, name=name, param_type=ptype))
        else:
            specs.append(SegmentSpec(raw=part, kind="static", name=part, param_type="str"))
    return specs


@dataclass
class RouteEntry:
    handler: Handler
    middlewares: list[Middleware] = field(default_factory=list)


@dataclass
class TrieNode:
    static_children: dict[str, "TrieNode"] = field(default_factory=dict)
    int_param_children: list[tuple[SegmentSpec, "TrieNode"]] = field(default_factory=list)
    str_param_children: list[tuple[SegmentSpec, "TrieNode"]] = field(default_factory=list)
    wildcard_children: list[tuple[SegmentSpec, "TrieNode"]] = field(default_factory=list)
    routes: dict[str, RouteEntry] = field(default_factory=dict)


@dataclass
class RouteMatch:
    node: TrieNode
    params: dict[str, Any]


class RouteTrie:
    def __init__(self) -> None:
        self.root = TrieNode()

    def insert(
        self,
        method: str,
        pattern: str,
        handler: Handler,
        middlewares: list[Middleware] | None = None,
    ) -> None:
        specs = parse_pattern(pattern)
        node = self.root
        for spec in specs:
            if spec.kind == "static":
                node = node.static_children.setdefault(spec.name, TrieNode())
            elif spec.kind == "param":
                target_list = (
                    node.int_param_children if spec.param_type == "int" else node.str_param_children
                )
                existing = next((child for s, child in target_list if s.name == spec.name), None)
                if existing is None:
                    existing = TrieNode()
                    target_list.append((spec, existing))
                node = existing
            elif spec.kind == "wildcard":
                existing = next(
                    (child for s, child in node.wildcard_children if s.name == spec.name), None
                )
                if existing is None:
                    existing = TrieNode()
                    node.wildcard_children.append((spec, existing))
                node = existing
        node.routes[method.upper()] = RouteEntry(
            handler=handler,
            middlewares=list(middlewares) if middlewares else [],
        )

    def match(self, path: str) -> RouteMatch | None:
        cleaned = path.strip("/")
        segments = [] if not cleaned else cleaned.split("/")
        return self._search(self.root, segments, 0, {})

    def _search(
        self,
        node: TrieNode,
        segments: list[str],
        index: int,
        params: dict[str, Any],
    ) -> RouteMatch | None:
        if index == len(segments):
            if node.routes:
                return RouteMatch(node=node, params=dict(params))
            return None

        seg = segments[index]

        if seg in node.static_children:
            res = self._search(node.static_children[seg], segments, index + 1, params)
            if res is not None:
                return res

        for spec, child in node.int_param_children:
            ok, val = spec.coerce(seg)
            if ok:
                next_params = dict(params)
                next_params[spec.name] = val
                res = self._search(child, segments, index + 1, next_params)
                if res is not None:
                    return res

        for spec, child in node.str_param_children:
            ok, val = spec.coerce(seg)
            if ok:
                next_params = dict(params)
                next_params[spec.name] = val
                res = self._search(child, segments, index + 1, next_params)
                if res is not None:
                    return res

        for spec, child in node.wildcard_children:
            remainder = "/".join(segments[index:])
            if remainder and child.routes:
                next_params = dict(params)
                next_params[spec.name] = remainder
                return RouteMatch(node=child, params=next_params)

        return None
