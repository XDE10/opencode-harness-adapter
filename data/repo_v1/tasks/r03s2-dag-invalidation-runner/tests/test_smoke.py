from r03s2pkg import TaskNode, TaskStatus, WorkflowEngine, WorkflowSpec


def test_linear_pipeline_execution():
    spec = WorkflowSpec(
        [
            TaskNode("extract"),
            TaskNode("transform", deps=("extract",)),
            TaskNode("load", deps=("transform",)),
        ]
    )
    engine = WorkflowEngine(spec)
    ledger = engine.run(
        {
            "extract": lambda _: [1, 2, 3],
            "transform": lambda up: [x * 10 for x in up["extract"]],
            "load": lambda up: sum(up["transform"]),
        }
    )
    assert ledger.outputs["load"] == 60
    assert ledger.by_status(TaskStatus.SUCCEEDED) == ["extract", "load", "transform"]


def test_retry_succeeds_on_second_attempt():
    attempts = {"count": 0}

    def flaky(_):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("transient error")
        return "ok"

    spec = WorkflowSpec([TaskNode("flaky", max_retries=1)])
    engine = WorkflowEngine(spec)
    ledger = engine.run({"flaky": flaky})
    assert ledger.records["flaky"].status == TaskStatus.SUCCEEDED
    assert ledger.records["flaky"].attempts == 2
    assert ledger.outputs["flaky"] == "ok"
