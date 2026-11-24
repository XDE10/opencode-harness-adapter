# Issue Report: DAG Workflow Runner (`r03s1dag`)

We are observing two separate defects in our workflow orchestration package `r03s1dag`:

1. **Duplicate / whitespace-padded dependency parsing and topological execution ordering**:
   When parsing workflow definitions via `parse_workflow(spec)`, dependency lists in DSL specifications sometimes include trailing whitespace around task IDs or duplicate references to the same upstream task (e.g. `"depends_on": ["extract ", "extract"]`). Currently, `parse_workflow` fails to deduplicate or normalize `depends_on` entries before constructing `TaskNode` instances. Downstream, the topological planner computes initial in-degrees from `node.depends_on`; duplicate dependency entries inflate the in-degree count so valid downstream nodes never reach in-degree 0, causing `topological_order` to falsely raise `CycleDetectedError`.

2. **Skip propagation and retry budget accounting in `WorkflowRunner`**:
   - `TaskNode.retries` specifies the number of **additional retry attempts** permitted after the initial execution attempt fails (so `retries=0` means 1 total attempt, `retries=2` means up to 3 total attempts).
   - When an upstream dependency ends in `TaskState.FAILED` or `TaskState.SKIPPED`, any downstream task should be marked `TaskState.SKIPPED` (with `attempts=0`, `output=None`, `error="upstream_failed"`) **unless** the downstream task has `allow_partial=True` AND **at least one** of its declared upstream dependencies succeeded (`TaskState.SUCCESS`). Currently, `WorkflowRunner` checks whether *all* dependencies failed/skipped or handles `allow_partial` and retry counts inconsistently.

## Complete Specification

### 1. Models (`r03s1dag.models`)
- `TaskState( str, Enum )`: `"PENDING"`, `"SUCCESS"`, `"FAILED"`, `"SKIPPED"`.
- `TaskNode`:
  - `task_id: str` (trimmed non-empty string)
  - `action: str`
  - `depends_on: tuple[str, ...]` (deduplicated, order-preserving tuple of trimmed upstream `task_id`s)
  - `retries: int = 0` (must be `>= 0`; number of retry attempts *after* initial attempt)
  - `allow_partial: bool = False`
- `LedgerEntry`:
  - `task_id: str`
  - `state: TaskState`
  - `attempts: int`
  - `output: Any = None`
  - `error: str | None = None`

### 2. Parser & Topological Planner (`r03s1dag.parser`)
- `parse_workflow(raw_tasks: list[dict[str, Any]]) -> dict[str, TaskNode]`:
  - Validates each dict has a non-empty string `id` (after `.strip()`) and `action`.
  - Trims whitespace on `id` and each element of `depends_on`, removing duplicate dependencies while preserving first-seen order.
  - Raises `ValueError` if duplicate task IDs exist, if `retries < 0`, if a task depends on itself, or if a dependency references an unknown task ID.
- `topological_order(nodes: dict[str, TaskNode]) -> list[str]`:
  - Returns task IDs in deterministic topological order: at each step, among all ready tasks (whose dependencies are all already scheduled), tie-break lexicographically by `task_id`.
  - Raises `CycleDetectedError` (a subclass of `ValueError`) if the graph contains a cycle.

### 3. Execution Engine (`r03s1dag.runner`)
- `WorkflowRunner(nodes: dict[str, TaskNode], handlers: dict[str, Callable[[dict[str, Any]], Any]])`:
  - Executes tasks in `topological_order(nodes)`.
  - Determining if a task with non-empty `depends_on` should run:
    - If `node.allow_partial` is `False`: all upstream dependencies in `node.depends_on` must have `state == TaskState.SUCCESS`. Otherwise, the task is skipped.
    - If `node.allow_partial` is `True`: at least one upstream dependency in `node.depends_on` must have `state == TaskState.SUCCESS`. If all upstream dependencies failed/skipped, the task is skipped.
  - When a task is skipped: record `LedgerEntry(task_id, TaskState.SKIPPED, attempts=0, output=None, error="upstream_failed")` and do not invoke its handler.
  - When a task runs: pass a context dict `{dep_id: ledger[dep_id].output for dep_id in node.depends_on if ledger[dep_id].state == TaskState.SUCCESS}` to `handlers[node.action]`.
  - Total maximum attempts is `1 + node.retries`. Stop retrying as soon as an attempt returns without raising an exception, recording `TaskState.SUCCESS`, `attempts=<attempts used>`, `output=<return value>`, `error=None`.
  - If all `1 + node.retries` attempts raise an exception, record `TaskState.FAILED`, `attempts=1 + node.retries`, `output=None`, `error=str(last_exc)`.
