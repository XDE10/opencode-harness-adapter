from r03s3pkg import NodeStatus, WorkflowExecutor, parse_workflow


def test_linear_workflow_execution():
    dsl = """
    extract
    transform -> extract
    load -> transform
    """
    spec = parse_workflow(dsl)
    executor = WorkflowExecutor(spec)
    ledger = executor.run(
        {
            "extract": lambda _: [1, 2, 3],
            "transform": lambda up: [x * 10 for x in up["extract"]],
            "load": lambda up: sum(up["transform"]),
        }
    )
    assert ledger.execution_order == ["extract", "transform", "load"]
    assert ledger.status_of("load") == NodeStatus.SUCCESS
    assert ledger.records["load"].output == 60


def test_failure_skips_downstream():
    dsl = """
    fetch
    process -> fetch
    """
    spec = parse_workflow(dsl)
    executor = WorkflowExecutor(spec)

    def fail_fetch(_):
        raise RuntimeError("network down")

    ledger = executor.run(
        {
            "fetch": fail_fetch,
            "process": lambda _: "done",
        }
    )
    assert ledger.status_of("fetch") == NodeStatus.FAILED
    assert ledger.status_of("process") == NodeStatus.SKIPPED
    assert ledger.records["process"].attempts == 0
