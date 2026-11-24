import pytest
from r03s1dag import (
    CycleDetectedError,
    TaskState,
    WorkflowRunner,
    parse_workflow,
    topological_order,
)


def test_deterministic_lexicographical_topological_order():
    spec = [
        {"id": "z_root", "action": "noop"},
        {"id": "a_root", "action": "noop"},
        {"id": "m_mid", "action": "noop", "depends_on": ["a_root"]},
        {"id": "b_mid", "action": "noop", "depends_on": ["a_root"]},
        {"id": "sink", "action": "noop", "depends_on": ["m_mid", "b_mid", "z_root"]},
    ]
    nodes = parse_workflow(spec)
    assert topological_order(nodes) == ["a_root", "b_mid", "m_mid", "z_root", "sink"]


def test_cycle_detection_raises():
    spec = [
        {"id": "a", "action": "noop", "depends_on": ["c"]},
        {"id": "b", "action": "noop", "depends_on": ["a"]},
        {"id": "c", "action": "noop", "depends_on": ["b"]},
    ]
    nodes = parse_workflow(spec)
    with pytest.raises(CycleDetectedError):
        topological_order(nodes)


def test_validation_errors_on_unknown_or_self_dependency():
    with pytest.raises(ValueError):
        parse_workflow([{"id": "a", "action": "noop", "depends_on": ["a"]}])

    with pytest.raises(ValueError):
        parse_workflow([{"id": "a", "action": "noop", "depends_on": ["missing"]}])


def test_parse_workflow_trims_and_deduplicates_dependencies():
    spec = [
        {"id": " extract ", "action": "act_extract"},
        {
            "id": "load",
            "action": "act_load",
            "depends_on": ["extract ", " extract", "extract"],
        },
    ]
    nodes = parse_workflow(spec)
    assert nodes["load"].depends_on == ("extract",)
    assert topological_order(nodes) == ["extract", "load"]


def test_duplicate_dependency_does_not_cause_false_cycle_in_runner():
    spec = [
        {"id": "t1", "action": "emit", "depends_on": []},
        {"id": "t2", "action": "combine", "depends_on": ["t1", "t1"]},
    ]
    nodes = parse_workflow(spec)
    runner = WorkflowRunner(
        nodes,
        handlers={
            "emit": lambda ctx: 10,
            "combine": lambda ctx: ctx["t1"] * 2,
        },
    )
    ledger = runner.run()
    assert ledger["t2"].state == TaskState.SUCCESS
    assert ledger["t2"].output == 20


def test_retries_count_is_additional_attempts_after_initial():
    spec = [
        {"id": "flaky", "action": "flaky_act", "retries": 1},
    ]
    nodes = parse_workflow(spec)
    calls = {"count": 0}

    def flaky_act(ctx):
        calls["count"] += 1
        if calls["count"] < 2:
            raise ValueError("temporary error")
        return "recovered"

    runner = WorkflowRunner(nodes, handlers={"flaky_act": flaky_act})
    ledger = runner.run()
    assert ledger["flaky"].state == TaskState.SUCCESS
    assert ledger["flaky"].attempts == 2
    assert ledger["flaky"].output == "recovered"


def test_retries_exhausted_records_total_attempts():
    spec = [
        {"id": "always_fails", "action": "fail_act", "retries": 2},
    ]
    nodes = parse_workflow(spec)
    calls = {"count": 0}

    def fail_act(ctx):
        calls["count"] += 1
        raise RuntimeError(f"fail #{calls['count']}")

    runner = WorkflowRunner(nodes, handlers={"fail_act": fail_act})
    ledger = runner.run()
    assert ledger["always_fails"].state == TaskState.FAILED
    assert ledger["always_fails"].attempts == 3
    assert ledger["always_fails"].error == "fail #3"


def test_allow_partial_runs_when_at_least_one_dependency_succeeds():
    spec = [
        {"id": "up_ok", "action": "ok_act"},
        {"id": "up_fail", "action": "fail_act"},
        {
            "id": "join",
            "action": "join_act",
            "depends_on": ["up_ok", "up_fail"],
            "allow_partial": True,
        },
    ]
    nodes = parse_workflow(spec)

    def fail_act(ctx):
        raise RuntimeError("upstream boom")

    runner = WorkflowRunner(
        nodes,
        handlers={
            "ok_act": lambda ctx: 42,
            "fail_act": fail_act,
            "join_act": lambda ctx: list(ctx.items()),
        },
    )
    ledger = runner.run()
    assert ledger["join"].state == TaskState.SUCCESS
    assert ledger["join"].output == [("up_ok", 42)]


def test_allow_partial_skips_when_all_dependencies_fail_or_skip():
    spec = [
        {"id": "up1", "action": "fail_act"},
        {"id": "up2", "action": "fail_act"},
        {
            "id": "join",
            "action": "join_act",
            "depends_on": ["up1", "up2"],
            "allow_partial": True,
        },
    ]
    nodes = parse_workflow(spec)

    def fail_act(ctx):
        raise RuntimeError("upstream boom")

    runner = WorkflowRunner(
        nodes,
        handlers={
            "fail_act": fail_act,
            "join_act": lambda ctx: "should_not_run",
        },
    )
    ledger = runner.run()
    assert ledger["up1"].state == TaskState.FAILED
    assert ledger["up2"].state == TaskState.FAILED
    assert ledger["join"].state == TaskState.SKIPPED
    assert ledger["join"].attempts == 0
    assert ledger["join"].error == "upstream_failed"
