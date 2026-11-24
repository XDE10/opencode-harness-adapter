import pytest
from r08s1pkg import (
    Version,
    SpecSet,
    Registry,
    LockPlanner,
    ResolutionConflictError,
)


def test_tilde_and_range_operators():
    spec = SpecSet("~1.4.2, <1.4.9")
    assert spec.matches("1.4.2")
    assert spec.matches("1.4.8")
    assert not spec.matches("1.4.9")
    assert not spec.matches("1.5.0")


def test_invalid_version_raises():
    with pytest.raises(ValueError):
        Version.parse("1.2")


def test_unresolvable_direct_conflict_raises():
    reg = Registry()
    reg.add_release("foo", "1.0.0")
    planner = LockPlanner(reg)
    with pytest.raises(ResolutionConflictError):
        planner.resolve({"foo": ">=2.0.0"})


def test_caret_zero_minor_semantics():
    spec = SpecSet("^0.2.3")
    assert spec.matches("0.2.3")
    assert spec.matches("0.2.9")
    assert not spec.matches("0.3.0")
    assert not spec.matches("0.2.2")


def test_caret_zero_patch_semantics():
    spec = SpecSet("^0.0.4")
    assert spec.matches("0.0.4")
    assert not spec.matches("0.0.5")
    assert not spec.matches("0.1.0")


def test_resolver_respects_zero_major_caret_boundaries():
    reg = Registry()
    reg.add_release("sdk", "0.3.0")
    reg.add_release("sdk", "0.2.5")
    reg.add_release("sdk", "0.2.1")
    reg.add_release("client", "1.0.0", {"sdk": "^0.2.1"})

    planner = LockPlanner(reg)
    locked = planner.resolve({"client": "^1.0.0"})
    assert locked == {
        "client": Version(1, 0, 0),
        "sdk": Version(0, 2, 5),
    }


def test_backtracking_discards_failed_candidate_constraints():
    reg = Registry()
    # web 2.0.0 requires Codec >=2.0.0, which conflicts with auth's Codec ^1.0.0
    # web 1.5.0 requires Codec ^1.0.0, which is compatible
    reg.add_release("web", "2.0.0", {"codec": ">=2.0.0"})
    reg.add_release("web", "1.5.0", {"codec": "^1.0.0"})
    reg.add_release("auth", "1.0.0", {"codec": "^1.0.0"})
    reg.add_release("codec", "2.0.0")
    reg.add_release("codec", "1.4.0")

    planner = LockPlanner(reg)
    locked = planner.resolve({"web": ">=1.0.0", "auth": "^1.0.0"})
    assert locked == {
        "auth": Version(1, 0, 0),
        "codec": Version(1, 4, 0),
        "web": Version(1, 5, 0),
    }


def test_backtracking_does_not_overconstrain_downstream_version():
    reg = Registry()
    # plugin-a 2.0.0 pins shared to =1.0.0, but fails later on missing driver 9.0.0
    # plugin-a 1.0.0 allows shared ^1.0.0 and driver ^1.0.0 -> shared should pick 1.3.0, not 1.0.0
    reg.add_release("plugin-a", "2.0.0", {"shared": "=1.0.0", "driver": "^9.0.0"})
    reg.add_release("plugin-a", "1.0.0", {"shared": "^1.0.0", "driver": "^1.0.0"})
    reg.add_release("shared", "1.3.0")
    reg.add_release("shared", "1.0.0")
    reg.add_release("driver", "1.1.0")

    planner = LockPlanner(reg)
    locked = planner.resolve({"plugin-a": ">=1.0.0"})
    assert locked == {
        "driver": Version(1, 1, 0),
        "plugin-a": Version(1, 0, 0),
        "shared": Version(1, 3, 0),
    }


def test_backtracking_with_zero_major_caret_combined():
    reg = Registry()
    reg.add_release("service", "0.4.1", {"proto": "^0.2.0", "transport": "^0.1.0"})
    reg.add_release("service", "0.4.0", {"proto": "^0.1.0", "transport": "^0.1.0"})
    reg.add_release("transport", "0.1.2", {"proto": "^0.1.2"})
    reg.add_release("proto", "0.2.0")
    reg.add_release("proto", "0.1.5")
    reg.add_release("proto", "0.1.1")

    planner = LockPlanner(reg)
    locked = planner.resolve({"service": "^0.4.0"})
    assert locked == {
        "proto": Version(0, 1, 5),
        "service": Version(0, 4, 0),
        "transport": Version(0, 1, 2),
    }
