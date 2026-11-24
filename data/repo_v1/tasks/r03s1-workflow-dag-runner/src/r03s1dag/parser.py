from typing import Any
from r03s1dag.models import CycleDetectedError, TaskNode


def parse_workflow(raw_tasks: list[dict[str, Any]]) -> dict[str, TaskNode]:
    nodes: dict[str, TaskNode] = {}
    for item in raw_tasks:
        raw_id = str(item.get("id", "")).strip()
        action = str(item.get("action", "")).strip()
        if not raw_id or not action:
            raise ValueError("Task 'id' and 'action' must be non-empty strings")
        if raw_id in nodes:
            raise ValueError(f"Duplicate task id: {raw_id}")

        retries = int(item.get("retries", 0))
        if retries < 0:
            raise ValueError(f"Negative retries not allowed for task {raw_id}")

        raw_deps = item.get("depends_on") or ()
        deps = tuple(str(d) for d in raw_deps)
        if raw_id in deps:
            raise ValueError(f"Task {raw_id} cannot depend on itself")

        nodes[raw_id] = TaskNode(
            task_id=raw_id,
            action=action,
            depends_on=deps,
            retries=retries,
            allow_partial=bool(item.get("allow_partial", False)),
        )

    for task_id, node in nodes.items():
        for dep in node.depends_on:
            if dep not in nodes:
                raise ValueError(f"Task {task_id} depends on unknown task {dep}")

    return nodes


def topological_order(nodes: dict[str, TaskNode]) -> list[str]:
    in_degree: dict[str, int] = {tid: 0 for tid in nodes}
    dependents: dict[str, list[str]] = {tid: [] for tid in nodes}

    for tid, node in nodes.items():
        for dep in node.depends_on:
            in_degree[tid] += 1
            if tid not in dependents[dep]:
                dependents[dep].append(tid)

    ready = sorted(tid for tid, deg in in_degree.items() if deg == 0)
    order: list[str] = []

    while ready:
        current = ready.pop(0)
        order.append(current)
        for nxt in dependents[current]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                ready.append(nxt)
        ready.sort()

    if len(order) != len(nodes):
        raise CycleDetectedError("Cycle detected in workflow graph")

    return order
