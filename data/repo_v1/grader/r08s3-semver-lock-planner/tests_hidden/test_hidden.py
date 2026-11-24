import pytest
from r08s3pkg import (
    Version,
    ConstraintSpec,
    PackageRegistry,
    DependencyResolver,
    ResolutionConflictError,
)


def test_tilde_and_compound_constraints():
    spec = ConstraintSpec.parse("~1.4.2, !=1.4.5")
    assert spec.matches(Version.parse("1.4.2"))
    assert spec.matches(Version.parse("1.4.9"))
    assert not spec.matches(Version.parse("1.4.5"))
    assert not spec.matches(Version.parse("1.5.0"))


def test_caret_zero_minor_constraint_boundaries():
    spec = ConstraintSpec.parse("^0.2.3")
    assert not spec.matches(Version.parse("0.2.2"))
    assert spec.matches(Version.parse("0.2.3"))
    assert spec.matches(Version.parse("0.2.9"))
    assert not spec.matches(Version.parse("0.3.0"))


def test_caret_zero_major_zero_minor_locks_patch():
    spec = ConstraintSpec.parse("^0.0.4")
    assert not spec.matches(Version.parse("0.0.3"))
    assert spec.matches(Version.parse("0.0.4"))
    assert not spec.matches(Version.parse("0.0.5"))
    assert not spec.matches(Version.parse("0.1.0"))


def test_resolver_respects_zero_minor_caret_in_registry():
    reg = PackageRegistry()
    reg.register("service", "1.0.0", {"codec": "^0.4.1"})
    reg.register("codec", "0.4.0")
    reg.register("codec", "0.4.5")
    reg.register("codec", "0.5.0")

    resolver = DependencyResolver(reg)
    plan = resolver.resolve({"service": "1.0.0"})
    assert plan.versions() == {"codec": "0.4.5", "service": "1.0.0"}


def test_backtracking_rolls_back_abandoned_transitive_constraints():
    reg = PackageRegistry()
    # api 2.0.0 requires core ==1.0.0 and plugin ==1.0.0, but plugin 1.0.0 requires core ==2.0.0 (conflict!)
    # api 1.0.0 requires core ^2.0.0 and no plugin, or compatible plugin
    reg.register("api", "2.0.0", {"core": "==1.0.0", "plugin": "==1.0.0"})
    reg.register("api", "1.0.0", {"core": ">=2.0.0"})
    reg.register("plugin", "1.0.0", {"core": "==2.0.0"})
    reg.register("core", "2.0.0")
    reg.register("core", "1.0.0")

    resolver = DependencyResolver(reg)
    plan = resolver.resolve({"api": ">=1.0.0"})
    assert plan.versions() == {"api": "1.0.0", "core": "2.0.0"}


def test_backtracking_discards_orphan_package_introduced_by_failed_branch():
    reg = PackageRegistry()
    # alpha 2.0.0 pulls in extra_dep ^1.0.0 and beta ==2.0.0 (which doesn't exist)
    # alpha 1.0.0 only pulls in beta ==1.0.0 (no extra_dep!)
    reg.register("alpha", "2.0.0", {"extra_dep": "^1.0.0", "beta": "==2.0.0"})
    reg.register("alpha", "1.0.0", {"beta": "==1.0.0"})
    reg.register("beta", "1.0.0")
    reg.register("extra_dep", "1.2.0")

    resolver = DependencyResolver(reg)
    plan = resolver.resolve({"alpha": ">=1.0.0"})
    assert plan.versions() == {"alpha": "1.0.0", "beta": "1.0.0"}
    assert "extra_dep" not in plan.versions()


def test_unresolvable_diamond_conflict_raises():
    reg = PackageRegistry()
    reg.register("web", "1.0.0", {"auth": "^1.0.0", "db": "^1.0.0"})
    reg.register("auth", "1.0.0", {"crypto": ">=2.0.0"})
    reg.register("db", "1.0.0", {"crypto": "<2.0.0"})
    reg.register("crypto", "1.5.0")
    reg.register("crypto", "2.1.0")

    resolver = DependencyResolver(reg)
    with pytest.raises(ResolutionConflictError):
        resolver.resolve({"web": "1.0.0"})


def test_topological_install_order_diamond():
    reg = PackageRegistry()
    reg.register("root", "1.0.0", {"left": "^1.0.0", "right": "^1.0.0"})
    reg.register("left", "1.1.0", {"base": "^1.0.0"})
    reg.register("right", "1.2.0", {"base": "^1.0.0"})
    reg.register("base", "1.4.0")

    resolver = DependencyResolver(reg)
    plan = resolver.resolve({"root": "1.0.0"})
    assert plan.install_order() == [
        ("base", Version(1, 4, 0)),
        ("left", Version(1, 1, 0)),
        ("right", Version(1, 2, 0)),
        ("root", Version(1, 0, 0)),
    ]
