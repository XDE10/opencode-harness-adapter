import pytest

from r05s2quota import PolicyRegistry, QuotaEnforcer, QuotaPolicy, SlidingWindowStore


def test_unconstrained_scope_and_validation() -> None:
    registry = PolicyRegistry()
    enforcer = QuotaEnforcer(registry)
    res = enforcer.acquire("untracked/tenant", "api_calls", 50, now=1000)
    assert res.allowed is True
    assert res.violated_scope is None
    assert res.remaining == {}

    with pytest.raises(ValueError):
        QuotaPolicy(scope="/leading", metric="m", limit=10, window_seconds=10)
    with pytest.raises(ValueError):
        enforcer.acquire("acme", "api_calls", -1, now=1000)


def test_sliding_window_inclusive_boundary() -> None:
    registry = PolicyRegistry()
    registry.register(QuotaPolicy(scope="org", metric="calls", limit=10, window_seconds=10))
    enforcer = QuotaEnforcer(registry)

    assert enforcer.acquire("org", "calls", 6, now=100).allowed is True
    assert enforcer.acquire("org", "calls", 5, now=109).allowed is False
    res = enforcer.acquire("org", "calls", 5, now=110)
    assert res.allowed is True
    assert res.remaining == {"org": 5}


def test_multi_level_chain_resolution_skips_unconfigured_levels() -> None:
    registry = PolicyRegistry()
    registry.register(QuotaPolicy(scope="org", metric="gpu", limit=100, window_seconds=60))
    registry.register(QuotaPolicy(scope="org/dept/team/user", metric="gpu", limit=20, window_seconds=60))
    chain = registry.resolve_chain("org/dept/team/user", "gpu")
    assert [p.scope for p in chain] == ["org", "org/dept/team/user"]


def test_policy_conflict_priority_and_restrictiveness_tiebreak() -> None:
    registry = PolicyRegistry()
    p_base = QuotaPolicy(scope="acme", metric="req", limit=100, window_seconds=10, priority=5)
    p_low_prio = QuotaPolicy(scope="acme", metric="req", limit=10, window_seconds=10, priority=2)
    p_same_prio_stricter_rate = QuotaPolicy(scope="acme", metric="req", limit=50, window_seconds=10, priority=5)
    p_same_prio_looser_rate = QuotaPolicy(scope="acme", metric="req", limit=200, window_seconds=10, priority=5)
    p_same_rate_smaller_burst = QuotaPolicy(scope="acme", metric="req", limit=25, window_seconds=5, priority=5)
    p_same_rate_larger_burst = QuotaPolicy(scope="acme", metric="req", limit=100, window_seconds=20, priority=5)

    registry.register(p_base)
    assert registry.register(p_low_prio) == p_base
    assert registry.register(p_same_prio_stricter_rate) == p_same_prio_stricter_rate
    assert registry.register(p_same_prio_looser_rate) == p_same_prio_stricter_rate
    assert registry.register(p_same_rate_smaller_burst) == p_same_rate_smaller_burst
    assert registry.register(p_same_rate_larger_burst) == p_same_rate_smaller_burst


def test_enforcer_uses_most_restrictive_winning_policy() -> None:
    registry = PolicyRegistry()
    registry.register(QuotaPolicy(scope="acme/api", metric="req", limit=50, window_seconds=60, priority=1))
    registry.register(QuotaPolicy(scope="acme/api", metric="req", limit=20, window_seconds=60, priority=1))
    registry.register(QuotaPolicy(scope="acme/api", metric="req", limit=80, window_seconds=60, priority=1))
    enforcer = QuotaEnforcer(registry)

    res_fail = enforcer.acquire("acme/api", "req", amount=25, now=10)
    assert res_fail.allowed is False
    assert res_fail.violated_scope == "acme/api"
    assert res_fail.remaining == {"acme/api": 20}


def test_leaf_violation_does_not_pollute_ancestor_usage() -> None:
    registry = PolicyRegistry()
    registry.register(QuotaPolicy(scope="acme", metric="tokens", limit=100, window_seconds=60))
    registry.register(QuotaPolicy(scope="acme/team", metric="tokens", limit=50, window_seconds=60))
    registry.register(QuotaPolicy(scope="acme/team/user", metric="tokens", limit=10, window_seconds=60))
    store = SlidingWindowStore()
    enforcer = QuotaEnforcer(registry, store)

    res = enforcer.acquire("acme/team/user", "tokens", amount=20, now=100)
    assert res.allowed is False
    assert res.violated_scope == "acme/team/user"
    assert res.remaining == {"acme": 100, "acme/team": 50, "acme/team/user": 10}

    assert store.current_usage("acme", "tokens", 60, now=100) == 0
    assert store.current_usage("acme/team", "tokens", 60, now=100) == 0
    assert store.current_usage("acme/team/user", "tokens", 60, now=100) == 0


def test_acquire_batch_rolls_back_all_steps_on_failure() -> None:
    registry = PolicyRegistry()
    registry.register(QuotaPolicy(scope="acme", metric="tokens", limit=100, window_seconds=60))
    registry.register(QuotaPolicy(scope="acme/team_a", metric="tokens", limit=60, window_seconds=60))
    registry.register(QuotaPolicy(scope="acme/team_b", metric="tokens", limit=60, window_seconds=60))
    store = SlidingWindowStore()
    enforcer = QuotaEnforcer(registry, store)

    batch_results = enforcer.acquire_batch(
        [
            ("acme/team_a", "tokens", 55),
            ("acme/team_b", "tokens", 55),
        ],
        now=200,
    )
    assert len(batch_results) == 2
    assert batch_results[0].allowed is True
    assert batch_results[1].allowed is False
    assert batch_results[1].violated_scope == "acme"

    assert store.current_usage("acme", "tokens", 60, now=200) == 0
    assert store.current_usage("acme/team_a", "tokens", 60, now=200) == 0
    assert store.current_usage("acme/team_b", "tokens", 60, now=200) == 0


def test_invalidate_subtree_boundary_and_metric_filter() -> None:
    registry = PolicyRegistry()
    for scope in ("acme", "acme/team", "acme_corp"):
        registry.register(QuotaPolicy(scope=scope, metric="calls", limit=100, window_seconds=60))
        registry.register(QuotaPolicy(scope=scope, metric="bytes", limit=100, window_seconds=60))
    store = SlidingWindowStore()
    enforcer = QuotaEnforcer(registry, store)

    enforcer.acquire("acme/team", "calls", 10, now=50)
    enforcer.acquire("acme/team", "bytes", 20, now=50)
    enforcer.acquire("acme_corp", "calls", 30, now=50)

    removed = enforcer.invalidate_subtree("acme", metric="calls")
    assert removed == 2
    assert store.current_usage("acme", "calls", 60, now=50) == 0
    assert store.current_usage("acme/team", "calls", 60, now=50) == 0
    assert store.current_usage("acme", "bytes", 60, now=50) == 20
    assert store.current_usage("acme_corp", "calls", 60, now=50) == 30
