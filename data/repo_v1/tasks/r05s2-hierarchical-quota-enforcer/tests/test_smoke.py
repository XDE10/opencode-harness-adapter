from r05s2quota import PolicyRegistry, QuotaEnforcer, QuotaPolicy


def test_single_scope_acquire_and_window_expiry() -> None:
    registry = PolicyRegistry()
    registry.register(QuotaPolicy(scope="acme", metric="requests", limit=10, window_seconds=60))
    enforcer = QuotaEnforcer(registry)

    res1 = enforcer.acquire("acme", "requests", amount=6, now=100)
    assert res1.allowed is True
    assert res1.remaining == {"acme": 4}

    res2 = enforcer.acquire("acme", "requests", amount=5, now=120)
    assert res2.allowed is False
    assert res2.violated_scope == "acme"

    res3 = enforcer.acquire("acme", "requests", amount=5, now=160)
    assert res3.allowed is True
    assert res3.remaining == {"acme": 5}


def test_hierarchical_resolution_happy_path() -> None:
    registry = PolicyRegistry()
    registry.register(QuotaPolicy(scope="acme", metric="tokens", limit=100, window_seconds=60))
    registry.register(QuotaPolicy(scope="acme/team", metric="tokens", limit=40, window_seconds=60))
    enforcer = QuotaEnforcer(registry)

    res = enforcer.acquire("acme/team/user1", "tokens", amount=25, now=10)
    assert res.allowed is True
    assert res.remaining == {"acme": 75, "acme/team": 15}
