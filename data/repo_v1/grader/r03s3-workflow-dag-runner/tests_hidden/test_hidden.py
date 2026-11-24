import pytest

from r03s3pkg import NodeSpec, NodeStatus, WorkflowExecutor, WorkflowSpec, parse_workflow


def test_diamond_dag_topological_lexicographical_order():
    dsl = """
    root
    branch_b -> root
    branch_a -> root
    join -> branch_a, branch_b
    """
    spec = parse_workflow(dsl)
    executor = WorkflowExecutor(spec)
    ledger = executor.run(
        {
            "root": lambda _: 10,
            "branch_a": lambda up: up["root"] + 1,
            "branch_b": lambda up: up["root"] + 2,
            "join": lambda up: up["branch_a"] * up["branch_b"],
        }
    )
    assert ledger.execution_order == ["root", "branch_a", "branch_b", "join"]
    assert ledger.records["join"].output == 11 * 12


def test_cycle_and_unknown_dependency_validation():
    with pytest.raises(ValueError, match="unknown node"):
        parse_workflow("a -> missing_node")

    with pytest.raises(ValueError, match="Cycle detected"):
        parse_workflow(
            """
            a -> b
            b -> c
            c -> a
            """
        )


def test_transitive_skip_propagation_on_standard_failure():
    dsl = """
    step1
    step2 -> step1
    step3 -> step2
    """
    spec = parse_workflow(dsl)
    executor = WorkflowExecutor(spec)

    def fail_step(_):
        raise ValueError("boom")

    ledger = executor.run(
        {
            "step1": fail_step,
            "step2": lambda _: "s2",
            "step3": lambda _: "s3",
        }
    )
    assert ledger.summary() == {
        "step1": "FAILED",
        "step2": "SKIPPED",
        "step3": "SKIPPED",
    }
    assert ledger.records["step1"].attempts == 1
    assert ledger.records["step2"].attempts == 0
    assert ledger.records["step3"].attempts == 0


def test_parse_options_on_nodes_with_dependencies():
    dsl = """
    seed | retries=1
    enrich -> seed | retries=3, allow_failure=true
    publish -> enrich | allow_failure=false
    """
    spec = parse_workflow(dsl)
    assert spec.nodes["seed"].retries == 1
    assert spec.nodes["seed"].allow_failure is False
    assert spec.nodes["enrich"].dependencies == ("seed",)
    assert spec.nodes["enrich"].retries == 3
    assert spec.nodes["enrich"].allow_failure is True
    assert spec.nodes["publish"].dependencies == ("enrich",)
    assert spec.nodes["publish"].retries == 0
    assert spec.nodes["publish"].allow_failure is False


def test_parse_invalid_options_on_dependent_node_raises():
    dsl = """
    a
    b -> a | retries=-1
    """
    with pytest.raises(ValueError):
        parse_workflow(dsl)

    dsl_unknown = """
    a
    b -> a | timeout=30
    """
    with pytest.raises(ValueError, match="Unknown option"):
        parse_workflow(dsl_unknown)


def test_retries_count_includes_initial_plus_retry_attempts():
    spec = WorkflowSpec(
        nodes={
            "flaky_one": NodeSpec("flaky_one", retries=1),
            "flaky_two": NodeSpec("flaky_two", dependencies=("flaky_one",), retries=2),
        }
    )
    executor = WorkflowExecutor(spec)
    state = {"one": 0, "two": 0}

    def run_one(_):
        state["one"] += 1
        if state["one"] < 2:
            raise RuntimeError("transient 1")
        return "ok1"

    def run_two(up):
        state["two"] += 1
        raise RuntimeError(f"permanent 2 after {up['flaky_one']}")

    ledger = executor.run({"flaky_one": run_one, "flaky_two": run_two})
    assert ledger.records["flaky_one"].status == NodeStatus.SUCCESS
    assert ledger.records["flaky_one"].attempts == 2
    assert ledger.records["flaky_one"].output == "ok1"

    assert ledger.records["flaky_two"].status == NodeStatus.FAILED
    assert ledger.records["flaky_two"].attempts == 3
    assert ledger.records["flaky_two"].error == "permanent 2 after ok1"


def test_allow_failure_permits_downstream_execution_with_none_output():
    spec = WorkflowSpec(
        nodes={
            "primary": NodeSpec("primary"),
            "optional_cache": NodeSpec("optional_cache", dependencies=("primary",), allow_failure=True),
            "finalize": NodeSpec("finalize", dependencies=("primary", "optional_cache")),
        }
    )
    executor = WorkflowExecutor(spec)

    def fail_cache(_):
        raise RuntimeError("cache miss")

    ledger = executor.run(
        {
            "primary": lambda _: 42,
            "optional_cache": fail_cache,
            "finalize": lambda up: (up["primary"], up["optional_cache"]),
        }
    )
    assert ledger.status_of("primary") == NodeStatus.SUCCESS
    assert ledger.status_of("optional_cache") == NodeStatus.FAILED
    assert ledger.status_of("finalize") == NodeStatus.SUCCESS
    assert ledger.records["finalize"].output == (42, None)


def test_end_to_end_dsl_with_retries_and_allow_failure():
    dsl = """
    init
    optional_step -> init | retries=1, allow_failure=true
    flaky_step -> optional_step | retries=2
    """
    spec = parse_workflow(dsl)
    executor = WorkflowExecutor(spec)
    counts = {"opt": 0, "flaky": 0}

    def run_opt(_):
        counts["opt"] += 1
        raise RuntimeError("opt failed")

    def run_flaky(up):
        counts["flaky"] += 1
        if counts["flaky"] < 3:
            raise RuntimeError("not yet")
        return f"recovered_with_{up['optional_step']}"

    ledger = executor.run(
        {
            "init": lambda _: "start",
            "optional_step": run_opt,
            "flaky_step": run_flaky,
        }
    )
    assert ledger.records["optional_step"].status == NodeStatus.FAILED
    assert ledger.records["optional_step"].attempts == 2
    assert ledger.records["flaky_step"].status == NodeStatus.SUCCESS
    assert ledger.records["flaky_step"].attempts == 3
    assert ledger.records["flaky_step"].output == "recovered_with_None"
