from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from r04s1pkg.models import Handler, Middleware, ParamSpec, RouteMatch


@dataclass
class RouteTarget:
    handler: Handler
    middlewares: list[Middleware] = field(default_factory=list)


@dataclass
class _TrieNode:
    static_children: dict[str, _TrieNode] = field(default_factory=dict)
    param_children: list[tuple[ParamSpec, _TrieNode]] = field(default_factory=list)
    wildcard_child: tuple[str, _TrieNode] | None = None
    targets: dict[str, RouteTarget] = field(default_factory=dict)


def split_path(path: str) -> list[str]:
    cleaned = path.strip()
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    stripped = cleaned.strip("/")
    if not stripped:
        return []
    return stripped.split("/")


class RouteTrie:
    def __init__(self) -> None:
        self.root = _TrieNode()

    def insert(
        self,
        method: str,
        pattern: str,
        handler: Handler,
        middlewares: list[Middleware] | None = None,
    ) -> None:
        segments = split_path(pattern)
        node = self.root
        for idx, seg in enumerate(segments):
            if seg.startswith("*"):
                if idx != len(segments) - 1:
                    raise ValueError("Wildcard segment must be at the end of pattern")
                wc_name = seg[1:].strip()
                if not wc_name:
                    raise ValueError("Wildcard segment must have a name")
                if node.wildcard_child is None:
                    node.wildcard_child = (wc_name, _TrieNode())
                node = node.wildcard_child[1]
                break
            elif seg.startswith("{") and seg.endswith("}"):
                spec = ParamSpec.parse(seg)
                existing = None
                for p_spec, p_node in node.param_children:
                    if p_spec == spec:
                        existing = p_node
                        break
                if existing is None:
                    existing = _TrieNode()
                    node.param_children.append((spec, existing))
                node = existing
            else:
                if seg not in node.static_children:
                    node.static_children[seg] = _TrieNode()
                node = node.static_children[seg]

        node.targets[method.upper()] = RouteTarget(
            handler=handler,
            middlewares=list(middlewares) if middlewares else [],
        )

    def match(self, method: str, path: str) -> RouteMatch | None:
        segments = split_path(path)
        method_up = method.upper()
        matched_node, params = self._search(self.root, segments, 0)
        if matched_node is None:
            return None
        allowed = set(matched_node.targets.keys())
        target = matched_node.targets.get(method_up)
        return RouteMatch(target=target, params=params, allowed_methods=allowed)

    def _search(
        self,
        node: _TrieNode,
        segments: list[str],
        idx: int,
    ) -> tuple[_TrieNode | None, dict[str, Any]]:
        if idx == len(segments):
            if node.targets:
                return node, {}
            if node.wildcard_child is not None:
                wc_name, wc_node = node.wildcard_child
                if wc_node.targets:
                    return wc_node, {wc_name: ""}
            return None, {}

        seg = segments[idx]

        if seg in node.static_children:
            found_node, found_params = self._search(node.static_children[seg], segments, idx + 1)
            if found_node is not None:
                return found_node, found_params

        for spec, p_node in node.param_children:
            ok, val = spec.coerce(seg)
            if not ok:
                return None, {}
            found_node, found_params = self._search(p_node, segments, idx + 1)
            if found_node is not None:
                merged = {spec.name: val}
                merged.update(found_params)
                return found_node, merged

        if node.wildcard_child is not None:
            wc_name, wc_node = node.wildcard_child
            if wc_node.targets:
                remainder = "/".join(segments[idx:])
                return wc_node, {wc_name: remainder}

        return None, {}
