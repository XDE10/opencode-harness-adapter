from r08s1pkg import Registry, LockPlanner, Version, SpecSet


def test_version_and_basic_caret_spec():
    spec = SpecSet("^1.2.0")
    assert spec.matches("1.2.0")
    assert spec.matches("1.9.3")
    assert not spec.matches("2.0.0")
    assert not spec.matches("1.1.9")


def test_simple_linear_resolution():
    reg = Registry()
    reg.add_release("app-core", "1.1.0", {"utils": "^1.0.0"})
    reg.add_release("app-core", "1.0.0", {"utils": "^1.0.0"})
    reg.add_release("utils", "1.2.0")
    reg.add_release("utils", "1.0.0")

    planner = LockPlanner(reg)
    lock = planner.resolve({"app-core": "^1.0.0"})
    assert lock == {
        "app-core": Version(1, 1, 0),
        "utils": Version(1, 2, 0),
    }
