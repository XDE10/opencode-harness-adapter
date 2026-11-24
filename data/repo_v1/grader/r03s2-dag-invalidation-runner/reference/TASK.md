# Issue Report: DAG Runner Dependency Merge & Downstream Invalidation Bugs

## Context
`r03s2pkg` is an in-memory DAG workflow planner and execution engine. It parses task specifications, merges incremental specification overrides, topologically executes tasks with retry support and skip propagation, and supports invalidating a node (with cascading rollback of downstream ledger entries) for incremental re-runs.

## Reported Symptoms
1. **Incremental spec merge drops upstream edges or mishandles `allow_partial_deps` overrides**:
   When `WorkflowSpec.merge_override(override_spec)` is called to layer incremental changes onto an existing workflow:
   - Adding a new dependency to an existing node via `merge_override` unexpectedly overwrites its previous dependencies instead of taking the deduplicated union in order, **unless** `replace_deps=True` is explicitly passed.
   - Furthermore, when `allow_partial_deps` is updated on an existing node in an override spec, the merged `TaskNode` retains the old boolean flag if the override value is `False`.

2. **Downstream skip propagation & transitive invalidation issues in `WorkflowEngine`**:
   - **Join-node skip propagation**: A node with `allow_partial_deps=True` should run as long as **at least one** of its upstream dependencies `SUCCEEDED` (and none are still `PENDING`), even if other upstream dependencies `FAILED` or were `SKIPPED`. Currently, `WorkflowEngine.run()` skips any node if *any* upstream dependency did not succeed, ignoring `allow_partial_deps=True`. (Note: if a node has dependencies and *all* of them failed/skipped, it must still be `SKIPPED` even when `allow_partial_deps=True`.)
   - **Transitive ledger invalidation**: Calling `WorkflowEngine.invalidate(node_id)` is supposed to reset `node_id` and **all transitively downstream nodes** (children, grandchildren, etc.) back to `PENDING` in the ledger and remove their cached outputs so a subsequent `.run()` re-executes them. Currently, `invalidate(node_id)` only resets `node_id` and its direct children (1 hop), leaving deeper descendants in a stale `SUCCEEDED`/`SKIPPED` state during re-runs.

## Behavioral Specification
- `TaskNode`:
  - `node_id: str`, `deps: tuple[str, ...] = ()`, `max_retries: int = 0`, `allow_partial_deps: bool = False`.
- `WorkflowSpec.merge_override(other: WorkflowSpec, replace_deps: bool = False) -> WorkflowSpec`:
  - Returns a new `WorkflowSpec` containing all nodes from `self` and `other`.
  - If a `node_id` exists only in `self` or only in `other`, include it as-is.
  - If a `node_id` exists in both:
    - When `replace_deps=True`, use `other.node.deps`.
    - When `replace_deps=False` (default), combine `self.node.deps` followed by any new dependencies from `other.node.deps` preserving first-seen order without duplicates.
    - `max_retries` and `allow_partial_deps` must always take the values from `other.node`.
- `WorkflowEngine.run(handlers: dict[str, Callable[[dict[str, Any]], Any]]) -> ExecutionLedger`:
  - Executes only nodes currently in `TaskStatus.PENDING` in topological order (tie-breaking lexicographically by `node_id`).
  - For a node with upstream `deps`:
    - If `allow_partial_deps=False`: all `deps` must have status `SUCCEEDED`, otherwise mark node `SKIPPED` (with `attempts=0`, `output=None`).
    - If `allow_partial_deps=True`: at least one upstream dependency in `deps` must have status `SUCCEEDED`, otherwise mark node `SKIPPED`.
  - When executing a node, pass a `dict` mapping each `SUCCEEDED` upstream `dep_id` to `ledger.outputs[dep_id]` into `handlers[node_id](upstream_outputs)`.
  - Retry up to `max_retries` additional times on exception (total attempts = `1 + max_retries`). If all attempts raise, mark `FAILED` and record `str(exc)` in `last_error`.
- `WorkflowEngine.invalidate(node_id: str) -> set[str]`:
  - Raises `KeyError` if `node_id` is not in the spec.
  - Finds `node_id` and all nodes transitively reachable downstream from `node_id`.
  - Resets each affected node's ledger record to `TaskStatus.PENDING` (`attempts=0`, `output=None`, `last_error=None`) and deletes its entry from `ledger.outputs` if present.
  - Returns the `set[str]` of all invalidated node IDs (including `node_id`).
