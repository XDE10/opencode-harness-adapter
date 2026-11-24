import pytest

from r03s2pkg import TaskNode, TaskStatus, TopologicalPlanner, WorkflowEngine, WorkflowSpec
from r03s2pkg.planner import CycleError


def test_topological_tie_breaking_and_cycle_detection():
    spec = WorkflowSpec(
        [
            TaskNode("c", deps=("a", "b")),
            TaskNode("b"),
            TaskNode("a"),
        ]
    )
    planner = TopologicalPlanner(spec)
    assert planner.topological_order() == ["a", "b", "c"]

    cyclic = WorkflowSpec(
        [
            TaskNode("a", deps=("b",)),
            TaskNode("b", deps=("a",)),
        ]
    )
    with pytest.raises(CycleError):
        TopologicalPlanner(cyclic).topological_order()


def test_strict_skip_propagation_on_upstream_failure():
    spec = WorkflowSpec(
        [
            TaskNode("root_fail", max_retries=1),
            TaskNode("child", deps=("root_fail",)),
            TaskNode("grandchild", deps=("child",)),
        ]
    )
    engine = WorkflowEngine(spec)

    def fail_always(_):
        raise ValueError("db down")

    ledger = engine.run(
        {
            "root_fail": fail_always,
            "child": lambda _: "should not run",
            "grandchild": lambda _: "should not run",
        }
    )
    assert ledger.records["root_fail"].status == TaskStatus.FAILED
    assert ledger.records["root_fail"].attempts == 2
    assert ledger.records["root_fail"].last_error == "db down"
    assert ledger.records["child"].status == TaskStatus.SKIPPED
    assert ledger.records["grandchild"].status == TaskStatus.SKIPPED


def test_unknown_dependency_raises_key_error():
    spec = WorkflowSpec([TaskNode("a", deps=("missing",))])
    with pytest.raises(KeyError):
        TopologicalPlanner(spec)


def test_merge_override_unions_dependencies_by_default():
    base = WorkflowSpec(
        [
            TaskNode("src_a"),
            TaskNode("src_b"),
            TaskNode("join", deps=("src_a",), max_retries=1),
        ]
    )
    override = WorkflowSpec(
        [
            TaskNode("src_c"),
            TaskNode("join", deps=("src_b", "src_a", "src_c"), max_retries=3),
        ]
    )
    merged = base.merge_override(override, replace_deps=False)
    join_node = merged.get_node("join")
    assert join_node.deps == ("src_a", "src_b", "src_c")
    assert join_node.max_retries == 3


def test_merge_override_replace_deps_and_false_flag_override():
    base = WorkflowSpec(
        [
            TaskNode("a"),
            TaskNode("b"),
            TaskNode("join", deps=("a", "b"), allow_partial_deps=True),
        ]
    )
    override = WorkflowSpec(
        [
            TaskNode("join", deps=("b",), allow_partial_deps=False),
        ]
    )
    merged = base.merge_override(override, replace_deps=True)
    join_node = merged.get_node("join")
    assert join_node.deps == ("b",)
    assert join_node.allow_partial_deps is False


def test_allow_partial_deps_executes_when_one_branch_succeeds():
    spec = WorkflowSpec(
        [
            TaskNode("primary"),
            TaskNode("secondary"),
            TaskNode("merge", deps=("primary", "secondary"), allow_partial_deps=True),
            TaskNode("final", deps=("merge",)),
        ]
    )
    engine = WorkflowEngine(spec)
    ledger = engine.run(
        {
            "primary": lambda _: (_ for _ in ()).throw(RuntimeError("primary timeout")),
            "secondary": lambda _: {"rows": 5},
            "merge": lambda up: ("from_partial", sorted(up.keys()), up["secondary"]["rows"]),
            "final": lambda up: up["merge"][2] * 2,
        }
    )
    assert ledger.records["primary"].status == TaskStatus.FAILED
    assert ledger.records["secondary"].status == TaskStatus.SUCCEEDED
    assert ledger.records["merge"].status == TaskStatus.SUCCEEDED
    assert ledger.outputs["merge"] == ("from_partial", ["secondary"], 5)
    assert ledger.records["final"].status == TaskStatus.SUCCEEDED
    assert ledger.outputs["final"] == 10


def test_allow_partial_deps_skips_when_all_branches_fail_or_skip():
    spec = WorkflowSpec(
        [
            TaskNode("b1"),
            TaskNode("b2", deps=("b1",)),
            TaskNode("join", deps=("b1", "b2"), allow_partial_deps=True),
        ]
    )
    engine = WorkflowEngine(spec)
    ledger = engine.run(
        {
            "b1": lambda _: (_ for _ in ()).throw(RuntimeError("b1 failed")),
            "b2": lambda _: "unreachable",
            "join": lambda _: "unreachable",
        }
    )
    assert ledger.records["b1"].status == TaskStatus.FAILED
    assert ledger.records["b2"].status == TaskStatus.SKIPPED
    assert ledger.records["join"].status == TaskStatus.SKIPPED
    assert "join" not in ledger.outputs


def test_transitive_invalidation_resets_multi_hop_descendants_and_reruns():
    spec = WorkflowSpec(
        [
            TaskNode("seed"),
            TaskNode("step1", deps=("seed",)),
            TaskNode("step2", deps=("step1",)),
            TaskNode("step3", deps=("step2",)),
            TaskNode("independent"),
        ]
    )
    state = {"multiplier": 2, "independent_runs": 0}
    handlers = {
        "seed": lambda _: 3,
        "step1": lambda up: up["seed"] + 1,
        "step2": lambda up: up["step1"] * state["multiplier"],
        "step3": lambda up: f"total={up['step2']}",
        "independent": lambda _: state.__setitem__("independent_runs", state["independent_runs"] + 1) or "ind",
    }

    engine = WorkflowEngine(spec)
    engine.run(handlers)
    assert engine.ledger.outputs["step3"] == "total=8"
    assert state["independent_runs"] == 1

    invalidated = engine.invalidate("step1")
    assert invalidated == {"step1", "step2", "step3"}
    for nid in ("step1", "step2", "step3"):
        assert engine.ledger.records[nid].status == TaskStatus.PENDING
        assert nid not in engine.ledger.outputs

    state["multiplier"] = 10
    engine.run(handlers)
    assert engine.ledger.outputs["step2"] == 40
    assert engine.ledger.outputs["step3"] == "total=40"
    assert state["independent_runs"] == 1
