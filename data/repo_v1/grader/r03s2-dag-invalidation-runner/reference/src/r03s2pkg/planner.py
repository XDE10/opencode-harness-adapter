from __future__ import annotations

from r03s2pkg.models import WorkflowSpec


class CycleError(ValueError):
    """Raised when the workflow graph contains a dependency cycle."""


class TopologicalPlanner:
    def __init__(self, spec: WorkflowSpec) -> None:
        self.spec = spec
        self._validate_references()

    def _validate_references(self) -> None:
        known = set(self.spec.nodes.keys())
        for nid, node in self.spec.nodes.items():
            for dep in node.deps:
                if dep not in known:
                    raise KeyError(f"Node '{nid}' depends on unknown node '{dep}'")

    def children_map(self) -> dict[str, list[str]]:
        children: dict[str, list[str]] = {nid: [] for nid in self.spec.nodes}
        for nid, node in self.spec.nodes.items():
            for dep in node.deps:
                children[dep].append(nid)
        for nid in children:
            children[nid].sort()
        return children

    def topological_order(self) -> list[str]:
        nodes = self.spec.nodes
        in_degree: dict[str, int] = {nid: len(node.deps) for nid, node in nodes.items()}
        children = self.children_map()
        ready = sorted(nid for nid, deg in in_degree.items() if deg == 0)
        order: list[str] = []

        while ready:
            current = ready.pop(0)
            order.append(current)
            for child in children[current]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    ready.append(child)
                    ready.sort()

        if len(order) != len(nodes):
            raise CycleError("Workflow graph contains a cycle")
        return order

    def downstream_closure(self, start_node_id: str) -> set[str]:
        if start_node_id not in self.spec.nodes:
            raise KeyError(f"Unknown node '{start_node_id}'")
        children = self.children_map()
        affected: set[str] = set()
        stack = [start_node_id]
        while stack:
            curr = stack.pop()
            if curr not in affected:
                affected.add(curr)
                stack.extend(children[curr])
        return affected
