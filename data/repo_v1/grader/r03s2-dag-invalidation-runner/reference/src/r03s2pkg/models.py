from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class TaskNode:
    node_id: str
    deps: tuple[str, ...] = ()
    max_retries: int = 0
    allow_partial_deps: bool = False

    def __post_init__(self) -> None:
        if not self.node_id or not isinstance(self.node_id, str):
            raise ValueError("node_id must be a non-empty string")
        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        deduped = tuple(dict.fromkeys(self.deps))
        object.__setattr__(self, "deps", deduped)


@dataclass
class NodeRecord:
    node_id: str
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    output: Any = None
    last_error: str | None = None


@dataclass
class ExecutionLedger:
    records: dict[str, NodeRecord] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)

    def ensure_node(self, node_id: str) -> NodeRecord:
        if node_id not in self.records:
            self.records[node_id] = NodeRecord(node_id=node_id)
        return self.records[node_id]

    def reset_node(self, node_id: str) -> None:
        self.records[node_id] = NodeRecord(node_id=node_id, status=TaskStatus.PENDING)
        self.outputs.pop(node_id, None)

    def by_status(self, status: TaskStatus) -> list[str]:
        return sorted(nid for nid, rec in self.records.items() if rec.status == status)


class WorkflowSpec:
    def __init__(self, nodes: list[TaskNode] | tuple[TaskNode, ...] = ()) -> None:
        self._nodes: dict[str, TaskNode] = {}
        for node in nodes:
            self._nodes[node.node_id] = node

    @property
    def nodes(self) -> dict[str, TaskNode]:
        return dict(self._nodes)

    def get_node(self, node_id: str) -> TaskNode:
        return self._nodes[node_id]

    def merge_override(self, other: WorkflowSpec, replace_deps: bool = False) -> WorkflowSpec:
        merged: dict[str, TaskNode] = dict(self._nodes)
        for nid, override_node in other.nodes.items():
            if nid not in merged:
                merged[nid] = override_node
            else:
                base_node = merged[nid]
                if replace_deps:
                    new_deps = override_node.deps
                else:
                    new_deps = tuple(dict.fromkeys(base_node.deps + override_node.deps))
                merged[nid] = TaskNode(
                    node_id=nid,
                    deps=new_deps,
                    max_retries=override_node.max_retries,
                    allow_partial_deps=override_node.allow_partial_deps,
                )
        return WorkflowSpec(list(merged.values()))
