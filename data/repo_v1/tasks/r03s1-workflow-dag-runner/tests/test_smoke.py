from r03s1dag import TaskState, WorkflowRunner, parse_workflow, topological_order


def test_linear_workflow_execution():
    spec = [
        {"id": "fetch", "action": "do_fetch"},
        {"id": "transform", "action": "do_transform", "depends_on": ["fetch"]},
    ]
    nodes = parse_workflow(spec)
    assert topological_order(nodes) == ["fetch", "transform"]

    runner = WorkflowRunner(
        nodes,
        handlers={
            "do_fetch": lambda ctx: [1, 2, 3],
            "do_transform": lambda ctx: sum(ctx["fetch"]),
        },
    )
    ledger = runner.run()
    assert ledger["fetch"].state == TaskState.SUCCESS
    assert ledger["transform"].state == TaskState.SUCCESS
    assert ledger["transform"].output == 6


def test_skip_on_upstream_failure():
    spec = [
        {"id": "step1", "action": "fail_action"},
        {"id": "step2", "action": "ok_action", "depends_on": ["step1"]},
    ]
    nodes = parse_workflow(spec)

    def fail_action(ctx):
        raise RuntimeError("boom")

    runner = WorkflowRunner(
        nodes,
        handlers={
            "fail_action": fail_action,
            "ok_action": lambda ctx: "done",
        },
    )
    ledger = runner.run()
    assert ledger["step1"].state == TaskState.FAILED
    assert ledger["step2"].state == TaskState.SKIPPED
    assert ledger["step2"].attempts == 0
