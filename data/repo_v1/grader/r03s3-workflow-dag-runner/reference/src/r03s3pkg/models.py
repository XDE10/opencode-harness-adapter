from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NodeStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    dependencies: tuple[str, ...] = ()
    retries: int = 0
    allow_failure: bool = False


@dataclass
class NodeRecord:
    node_id: str
    status: NodeStatus
    attempts: int
    output: Any = None
    error: str | None = None


@dataclass
class WorkflowSpec:
    nodes: dict[str, NodeSpec]


@dataclass
class ExecutionLedger:
    records: dict[str, NodeRecord] = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)

    def record(self, rec: NodeRecord) -> None:
        self.records[rec.node_id] = rec
        self.execution_order.append(rec.node_id)

    def status_of(self, node_id: str) -> NodeStatus:
        return self.records[node_id].status

    def summary(self) -> dict[str, str]:
        return {nid: rec.status.value for nid, rec in self.records.items()}
