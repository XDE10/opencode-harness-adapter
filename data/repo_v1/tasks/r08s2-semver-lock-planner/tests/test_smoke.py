from r08s2pkg import Version, ConstraintSpec, PackageRegistry, LockfilePlanner


def test_version_ordering_and_basic_tilde():
    v1 = Version.parse("1.2.0")
    v2 = Version.parse("1.2.9")
    v3 = Version.parse("1.3.0")
    spec = ConstraintSpec.parse("~1.2.0")
    assert v1 < v2 < v3
    assert spec.matches(v1)
    assert spec.matches(v2)
    assert not spec.matches(v3)


def test_simple_linear_resolution():
    reg = PackageRegistry()
    reg.register("app", "1.0.0", {"http": "^1.0.0"})
    reg.register("http", "1.1.0", {"core": ">=1.0.0,<2.0.0"})
    reg.register("http", "1.4.2", {"core": ">=1.0.0,<2.0.0"})
    reg.register("core", "1.5.0")

    planner = LockfilePlanner(reg)
    lock = planner.resolve({"app": "^1.0.0"})
    assert lock == {
        "app": "1.0.0",
        "core": "1.5.0",
        "http": "1.4.2",
    }
