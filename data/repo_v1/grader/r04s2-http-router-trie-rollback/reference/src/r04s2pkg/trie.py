from __future__ import annotations

from dataclasses import dataclass, field
from r04s2pkg.models import RouteConflictError, RouteEntry, RouteMatch


def split_path(path: str) -> list[str]:
    stripped = path.strip("/")
    return stripped.split("/") if stripped else []


def normalize_pattern(pattern: str) -> str:
    segs = split_path(pattern)
    return "/" + "/".join(segs) if segs else "/"


@dataclass
class TrieNode:
    static_children: dict[str, TrieNode] = field(default_factory=dict)
    param_name: str | None = None
    param_child: TrieNode | None = None
    wildcard_name: str | None = None
    wildcard_child: TrieNode | None = None
    handlers: dict[str, RouteEntry] = field(default_factory=dict)


class RouteTrie:
    def __init__(self) -> None:
        self.root = TrieNode()

    def insert(self, entry: RouteEntry) -> None:
        segments = split_path(entry.pattern)
        node = self.root
        for idx, seg in enumerate(segments):
            if seg.startswith("*"):
                if idx != len(segments) - 1:
                    raise ValueError("Wildcard segment must be the final segment")
                w_name = seg[1:] or "wildcard"
                if node.wildcard_child is None:
                    node.wildcard_name = w_name
                    node.wildcard_child = TrieNode()
                node = node.wildcard_child
            elif seg.startswith(":"):
                p_name = seg[1:]
                if node.param_child is None:
                    node.param_name = p_name
                    node.param_child = TrieNode()
                node = node.param_child
            else:
                if seg not in node.static_children:
                    node.static_children[seg] = TrieNode()
                node = node.static_children[seg]

        method = entry.method.upper()
        if method in node.handlers:
            raise RouteConflictError(f"Conflict for {method} {entry.pattern}")
        node.handlers[method] = entry

    def remove(self, method: str, pattern: str) -> bool:
        segments = split_path(pattern)
        node = self.root
        for seg in segments:
            if seg.startswith("*"):
                if node.wildcard_child is None:
                    return False
                node = node.wildcard_child
            elif seg.startswith(":"):
                if node.param_child is None:
                    return False
                node = node.param_child
            else:
                if seg not in node.static_children:
                    return False
                node = node.static_children[seg]
        return node.handlers.pop(method.upper(), None) is not None

    def match(self, path: str) -> RouteMatch | None:
        segments = split_path(path)
        params: dict[str, str] = {}
        matched_node = self._search(self.root, segments, 0, params)
        if matched_node is None:
            return None
        return RouteMatch(node_handlers=matched_node.handlers, params=params)

    def _search(
        self,
        node: TrieNode,
        segments: list[str],
        index: int,
        params: dict[str, str],
    ) -> TrieNode | None:
        if index == len(segments):
            return node if node.handlers else None

        seg = segments[index]
        if seg in node.static_children:
            res = self._search(node.static_children[seg], segments, index + 1, params)
            if res is not None:
                return res

        if node.param_child is not None and node.param_name is not None:
            had_prev = node.param_name in params
            prev_val = params.get(node.param_name)
            params[node.param_name] = seg
            res = self._search(node.param_child, segments, index + 1, params)
            if res is not None:
                return res
            if had_prev and prev_val is not None:
                params[node.param_name] = prev_val
            else:
                params.pop(node.param_name, None)

        if node.wildcard_child is not None and node.wildcard_name is not None:
            if node.wildcard_child.handlers:
                params[node.wildcard_name] = "/".join(segments[index:])
                return node.wildcard_child

        return None
