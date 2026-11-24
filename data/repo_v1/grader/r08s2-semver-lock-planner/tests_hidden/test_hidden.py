import pytest
from r08s2pkg import (
    Version,
    ConstraintSpec,
    PackageRegistry,
    LockfilePlanner,
    ResolutionConflictError,
)


def test_compound_range_and_inequality_constraints():
    spec = ConstraintSpec.parse(">=1.2.0, <2.0.0, !=1.5.0")
    assert spec.matches(Version.parse("1.2.0"))
    assert spec.matches(Version.parse("1.9.9"))
    assert not spec.matches(Version.parse("1.5.0"))
    assert not spec.matches(Version.parse("2.0.0"))


def test_caret_nonzero_major():
    spec = ConstraintSpec.parse("^2.3.1")
    assert spec.matches(Version.parse("2.3.1"))
    assert spec.matches(Version.parse("2.9.0"))
    assert not spec.matches(Version.parse("2.3.0"))
    assert not spec.matches(Version.parse("3.0.0"))


def test_unresolvable_graph_raises_conflict_error():
    reg = PackageRegistry()
    reg.register("service", "1.0.0", {"db": ">=2.0.0"})
    reg.register("worker", "1.0.0", {"db": "<2.0.0"})
    reg.register("db", "1.5.0")
    reg.register("db", "2.1.0")

    planner = LockfilePlanner(reg)
    with pytest.raises(ResolutionConflictError):
        planner.resolve({"service": "1.0.0", "worker": "1.0.0"})


def test_missing_package_in_registry_raises_conflict():
    reg = PackageRegistry()
    reg.register("cli", "1.0.0", {"nonexistent": "^1.0.0"})
    planner = LockfilePlanner(reg)
    with pytest.raises(ResolutionConflictError):
        planner.resolve({"cli": "1.0.0"})


def test_caret_zero_major_nonzero_minor_bounds():
    spec = ConstraintSpec.parse("^0.2.3")
    assert spec.matches(Version.parse("0.2.3"))
    assert spec.matches(Version.parse("0.2.9"))
    assert not spec.matches(Version.parse("0.2.2"))
    assert not spec.matches(Version.parse("0.3.0"))
    assert not spec.matches(Version.parse("0.9.0"))


def test_caret_zero_major_zero_minor_locks_patch():
    spec = ConstraintSpec.parse("^0.0.4")
    assert spec.matches(Version.parse("0.0.4"))
    assert not spec.matches(Version.parse("0.0.3"))
    assert not spec.matches(Version.parse("0.0.5"))
    assert not spec.matches(Version.parse("0.1.0"))


def test_resolver_respects_zero_major_caret_boundaries():
    reg = PackageRegistry()
    reg.register("sdk", "1.0.0", {"proto": "^0.3.1"})
    reg.register("proto", "0.3.1")
    reg.register("proto", "0.3.8")
    reg.register("proto", "0.4.0")

    planner = LockfilePlanner(reg)
    resolved = planner.resolve({"sdk": "^1.0.0"})
    assert resolved == {"proto": "0.3.8", "sdk": "1.0.0"}


def test_backtracking_rolls_back_mutated_constraints_from_failed_branch():
    reg = PackageRegistry()
    reg.register("alpha", "2.0.0", {"gamma": ">=2.0.0"})
    reg.register("alpha", "1.0.0", {"gamma": ">=1.0.0,<2.0.0"})
    reg.register("beta", "1.0.0", {"gamma": "<2.0.0"})
    reg.register("gamma", "2.1.0")
    reg.register("gamma", "1.4.0")

    planner = LockfilePlanner(reg)
    resolved = planner.resolve({"alpha": ">=1.0.0", "beta": "1.0.0"})
    assert resolved == {
        "alpha": "1.0.0",
        "beta": "1.0.0",
        "gamma": "1.4.0",
    }


def test_backtracking_prunes_orphan_transitive_packages_from_abandoned_candidate():
    reg = PackageRegistry()
    reg.register("alpha", "2.0.0", {"core": ">=2.0.0", "legacy_plugin": "^1.0.0"})
    reg.register("alpha", "1.0.0", {"core": ">=1.0.0,<2.0.0"})
    reg.register("core", "2.0.0")
    reg.register("core", "1.5.0")
    reg.register("legacy_plugin", "1.2.0")
    reg.register("zeta", "1.0.0", {"core": "<2.0.0"})

    planner = LockfilePlanner(reg)
    resolved = planner.resolve({"alpha": ">=1.0.0", "zeta": "1.0.0"})
    assert resolved == {
        "alpha": "1.0.0",
        "core": "1.5.0",
        "zeta": "1.0.0",
    }
    assert "legacy_plugin" not in resolved
