from collections.abc import Callable
from typing import Any

from r03s3pkg.models import ExecutionLedger, NodeRecord, NodeSpec, NodeStatus, WorkflowSpec


class WorkflowExecutor:
    def __init__(self, spec: WorkflowSpec) -> None:
        self.spec = spec

    def topological_order(self) -> list[str]:
        in_degree: dict[str, int] = {nid: len(spec.dependencies) for nid, spec in self.spec.nodes.items()}
        dependents: dict[str, list[str]] = {nid: [] for nid in self.spec.nodes}
        for nid, spec in self.spec.nodes.items():
            for dep in spec.dependencies:
                dependents[dep].append(nid)

        ready = sorted(nid for nid, deg in in_degree.items() if deg == 0)
        order: list[str] = []

        while ready:
            current = ready.pop(0)
            order.append(current)
            for nxt in dependents[current]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    ready.append(nxt)
            ready.sort()

        if len(order) != len(self.spec.nodes):
            raise ValueError("Workflow graph contains a cycle")
        return order

    def _should_skip(self, node: NodeSpec, ledger: ExecutionLedger) -> bool:
        for dep_id in node.dependencies:
            dep_rec = ledger.records[dep_id]
            if dep_rec.status == NodeStatus.SKIPPED:
                return True
            if dep_rec.status == NodeStatus.FAILED:
                return True
        return False

    def run(
        self,
        handlers: dict[str, Callable[[dict[str, Any]], Any]],
    ) -> ExecutionLedger:
        ledger = ExecutionLedger()
        for nid in self.topological_order():
            node = self.spec.nodes[nid]
            if self._should_skip(node, ledger):
                ledger.record(
                    NodeRecord(
                        node_id=nid,
                        status=NodeStatus.SKIPPED,
                        attempts=0,
                        output=None,
                        error=None,
                    )
                )
                continue

            if nid not in handlers:
                raise KeyError(f"Missing handler for node {nid!r}")

            upstream_outputs = {
                dep_id: ledger.records[dep_id].output for dep_id in node.dependencies
            }

            max_attempts = max(1, node.retries)
            attempts = 0
            last_error: str | None = None
            output: Any = None
            succeeded = False

            while attempts < max_attempts:
                attempts += 1
                try:
                    output = handlers[nid](upstream_outputs)
                    succeeded = True
                    last_error = None
                    break
                except Exception as exc:
                    last_error = str(exc)

            status = NodeStatus.SUCCESS if succeeded else NodeStatus.FAILED
            ledger.record(
                NodeRecord(
                    node_id=nid,
                    status=status,
                    attempts=attempts,
                    output=output if succeeded else None,
                    error=last_error,
                )
            )

        return ledger
