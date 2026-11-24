# Issue Report: DAG Workflow Runner Parser & Execution Ledger Regressions

## Overview
`r03s3pkg` parses declarative text specifications into a Directed Acyclic Graph (`WorkflowSpec`) and executes them in topological order via `WorkflowExecutor`, recording per-node status, attempt count, and output payloads in an `ExecutionLedger`.

Recently, two issues surfaced when running multi-stage workflows in staging:

1. **Inline Options & Dependencies Parsing (`parse_workflow`)**:
   - Each node line in a workflow DSL string follows the format:
     `node_id [-> dep1, dep2] [| key=val, key2=val2]`
   - Both the dependency clause (`-> ...`) and options clause (`| ...`) are optional.
   - Supported options are:
     - `retries=<int>` (default `0`): number of **additional** retry attempts permitted after the initial execution attempt fails.
     - `allow_failure=<bool>` (`true` / `false`, case-insensitive, default `false`): if `true`, a terminal failure of this node does **not** cause downstream dependent nodes to be skipped.
   - When a node line defines options (`| ...`) *with or without* dependencies, or when multiple options are comma-separated, `parse_workflow` fails to properly strip and parse option keys/values (specifically `allow_failure` and `retries` when combined or whitespace-padded, or when `->` follows/precedes `|`). Note: In the DSL grammar, `-> deps` always appears before `| options` if both are present, or `| options` may appear alone without `->`. Furthermore, dependencies declared via `->` are currently being stored in the wrong direction or not deduplicated when building `NodeSpec.dependencies`, or option values like `retries` are being misinterpreted during execution.
   - Specifically, verify how `NodeSpec.retries` is populated by `parse_workflow`: `retries=2` in DSL must mean 1 initial attempt + up to 2 retry attempts (total 3 max attempts), and `allow_failure=true` must set `NodeSpec.allow_failure = True`.

2. **Retry Accounting & Downstream Skip Propagation (`WorkflowExecutor.run`)**:
   - Topological execution order must be deterministic: at each step, among all ready nodes (whose dependencies have all completed), execute in lexicographical order of `node_id`.
   - For each ready node:
     - If **any** of its upstream dependencies ended in `NodeStatus.SKIPPED`, or ended in `NodeStatus.FAILED` **and** that dependency has `allow_failure=False`, the current node must not execute its handler; instead it is immediately recorded in the ledger with `status=NodeStatus.SKIPPED`, `attempts=0`, `output=None`, and `error=None`.
     - If an upstream dependency ended in `NodeStatus.FAILED` **but** that dependency has `allow_failure=True`, it does **not** block downstream nodes (the upstream failure is tolerated, and the downstream node receives `None` for that dependency's output in `upstream_outputs`).
   - When executing a node's handler `handler(upstream_outputs)`:
     - `upstream_outputs` is a `dict[str, Any]` mapping each direct dependency `dep_id` to its recorded output (`None` if the dependency failed with `allow_failure=True`).
     - A node with `retries=R` may run at most `1 + R` total attempts.
     - If an attempt raises an exception, retry until it succeeds or `1 + R` attempts are exhausted.
     - Record the exact number of attempts actually executed (`1` on first-try success, `1 + R` if all attempts fail), the final `NodeStatus` (`SUCCESS` or `FAILED`), `output` (on success), and `str(exc)` in `error` (on final failure).

## Expected Public API
- `NodeStatus` (`Enum`: `PENDING`, `SUCCESS`, `FAILED`, `SKIPPED`)
- `NodeSpec(node_id: str, dependencies: tuple[str, ...], retries: int = 0, allow_failure: bool = False)`
- `NodeRecord(node_id: str, status: NodeStatus, attempts: int, output: Any = None, error: str | None = None)`
- `WorkflowSpec(nodes: dict[str, NodeSpec])`
- `parse_workflow(dsl_text: str) -> WorkflowSpec`
  - Raises `ValueError` if a line is malformed, if a dependency references an unknown node, or if the graph contains a cycle.
- `WorkflowExecutor(spec: WorkflowSpec)`
  - `.run(handlers: dict[str, Callable[[dict[str, Any]], Any]]) -> ExecutionLedger`
