from typing import Any, Callable
from r03s1dag.models import LedgerEntry, TaskNode, TaskState
from r03s1dag.parser import topological_order


class WorkflowRunner:
    def __init__(
        self,
        nodes: dict[str, TaskNode],
        handlers: dict[str, Callable[[dict[str, Any]], Any]],
    ) -> None:
        self.nodes = nodes
        self.handlers = handlers

    def _should_skip(self, node: TaskNode, ledger: dict[str, LedgerEntry]) -> bool:
        if not node.depends_on:
            return False
        states = [ledger[dep].state for dep in node.depends_on]
        if node.allow_partial:
            return not any(s == TaskState.SUCCESS for s in states)
        return any(s != TaskState.SUCCESS for s in states)

    def run(self) -> dict[str, LedgerEntry]:
        order = topological_order(self.nodes)
        ledger: dict[str, LedgerEntry] = {}

        for tid in order:
            node = self.nodes[tid]
            if self._should_skip(node, ledger):
                ledger[tid] = LedgerEntry(
                    task_id=tid,
                    state=TaskState.SKIPPED,
                    attempts=0,
                    output=None,
                    error="upstream_failed",
                )
                continue

            handler = self.handlers[node.action]
            upstream_ctx = {
                dep: ledger[dep].output
                for dep in node.depends_on
                if ledger[dep].state == TaskState.SUCCESS
            }

            max_attempts = 1 + node.retries
            attempts = 0
            last_error: str | None = None
            succeeded = False
            result: Any = None

            while attempts < max_attempts:
                attempts += 1
                try:
                    result = handler(upstream_ctx)
                    succeeded = True
                    break
                except Exception as exc:
                    last_error = str(exc)

            if succeeded:
                ledger[tid] = LedgerEntry(
                    task_id=tid,
                    state=TaskState.SUCCESS,
                    attempts=attempts,
                    output=result,
                    error=None,
                )
            else:
                ledger[tid] = LedgerEntry(
                    task_id=tid,
                    state=TaskState.FAILED,
                    attempts=attempts,
                    output=None,
                    error=last_error,
                )

        return ledger
