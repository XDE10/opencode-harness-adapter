from r08s3pkg import PackageRegistry, DependencyResolver, Version, ConstraintSpec


def test_version_and_basic_range():
    spec = ConstraintSpec.parse(">=1.2.0, <2.0.0")
    assert spec.matches(Version.parse("1.2.0"))
    assert spec.matches(Version.parse("1.9.5"))
    assert not spec.matches(Version.parse("2.0.0"))


def test_simple_linear_resolution():
    reg = PackageRegistry()
    reg.register("app", "1.0.0", {"utils": "^1.1.0"})
    reg.register("utils", "1.0.0")
    reg.register("utils", "1.3.2")
    reg.register("utils", "2.0.0")

    resolver = DependencyResolver(reg)
    plan = resolver.resolve({"app": "^1.0.0"})
    assert plan.versions() == {"app": "1.0.0", "utils": "1.3.2"}
    assert plan.install_order() == [
        ("utils", Version(1, 3, 2)),
        ("app", Version(1, 0, 0)),
    ]
