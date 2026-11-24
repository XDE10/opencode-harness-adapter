from __future__ import annotations

from typing import Any, Callable

from r03s2pkg.models import ExecutionLedger, TaskNode, TaskStatus, WorkflowSpec
from r03s2pkg.planner import TopologicalPlanner


class WorkflowEngine:
    def __init__(self, spec: WorkflowSpec, ledger: ExecutionLedger | None = None) -> None:
        self.spec = spec
        self.planner = TopologicalPlanner(spec)
        self.ledger = ledger if ledger is not None else ExecutionLedger()
        for nid in self.spec.nodes:
            self.ledger.ensure_node(nid)

    def _should_skip(self, node: TaskNode) -> bool:
        if not node.deps:
            return False
        dep_statuses = [self.ledger.ensure_node(dep).status for dep in node.deps]
        if node.allow_partial_deps:
            return not any(st == TaskStatus.SUCCEEDED for st in dep_statuses)
        return any(st != TaskStatus.SUCCEEDED for st in dep_statuses)

    def _gather_inputs(self, node: TaskNode) -> dict[str, Any]:
        inputs: dict[str, Any] = {}
        for dep in node.deps:
            rec = self.ledger.ensure_node(dep)
            if rec.status == TaskStatus.SUCCEEDED:
                inputs[dep] = self.ledger.outputs.get(dep)
        return inputs

    def invalidate(self, node_id: str) -> set[str]:
        affected = self.planner.downstream_closure(node_id)
        for nid in affected:
            self.ledger.reset_node(nid)
        return affected

    def run(self, handlers: dict[str, Callable[[dict[str, Any]], Any]]) -> ExecutionLedger:
        order = self.planner.topological_order()
        for nid in order:
            rec = self.ledger.ensure_node(nid)
            if rec.status != TaskStatus.PENDING:
                continue

            node = self.spec.get_node(nid)
            if self._should_skip(node):
                rec.status = TaskStatus.SKIPPED
                rec.attempts = 0
                rec.output = None
                rec.last_error = None
                self.ledger.outputs.pop(nid, None)
                continue

            if nid not in handlers:
                raise KeyError(f"Missing execution handler for node '{nid}'")

            handler = handlers[nid]
            upstream_inputs = self._gather_inputs(node)
            max_attempts = 1 + node.max_retries
            rec.attempts = 0
            rec.last_error = None

            for attempt in range(1, max_attempts + 1):
                rec.attempts = attempt
                try:
                    result = handler(upstream_inputs)
                except Exception as exc:
                    rec.last_error = str(exc)
                    rec.status = TaskStatus.FAILED
                else:
                    rec.status = TaskStatus.SUCCEEDED
                    rec.output = result
                    rec.last_error = None
                    self.ledger.outputs[nid] = result
                    break

        return self.ledger
